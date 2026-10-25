"""Fixed event-time windows over stored measurement history as PHM model steps (ADR-0032).

One per-channel summary builds both the reference rows of an operator-built package and the steps
the package later scores, so a model never sees features computed two ways. Values are read at a
recorded DuckLake snapshot; every step keeps that snapshot and a digest of the values it used.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.phm_analysis import (
    PhmBinding,
    PreparedStep,
    SqlitePhmAnalysisStore,
    run_binding,
)
from industrial_phm.application.phm_runner import BindingCycle, PackageCache
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelPackageError,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    load_model_package,
    write_model_package,
)

FEATURE_SET_PREFIX = "history-window-stats-v1"
STATS = ("mean", "std", "min", "max")
WINDOW_SECONDS = (300, 600, 1800, 3600)
MIN_VALUES = 3
MIN_REFERENCE_WINDOWS = 24
MAX_CHANNELS = 8
RECIPE_ID = "operator-history-iforest-v1"
THRESHOLD_QUANTILE = 0.995
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class HistoryReader(Protocol):
    def current_snapshot_id(self) -> int: ...

    def history_channel_extent(
        self, asset_id: str, channel_ids: Sequence[str]
    ) -> tuple[datetime, datetime] | None: ...

    def query_channel_observations(
        self,
        asset_id: str,
        *,
        source_id: str,
        channel_ids: Sequence[str],
        start_at: datetime,
        end_at: datetime,
        snapshot_id: int,
        max_rows: int = ...,
    ) -> tuple[ChannelObservation, ...]: ...


def feature_set_id(window_seconds: int) -> str:
    if window_seconds not in WINDOW_SECONDS:
        raise ValueError(f"window length must be one of {WINDOW_SECONDS} seconds")
    return f"{FEATURE_SET_PREFIX}:{window_seconds}s"


def window_seconds_of(feature_set: str) -> int | None:
    """The window length a history-window feature set declares, or None for another set."""
    prefix = FEATURE_SET_PREFIX + ":"
    if not feature_set.startswith(prefix) or not feature_set.endswith("s"):
        return None
    try:
        seconds = int(feature_set[len(prefix) : -1])
    except ValueError:
        return None
    return seconds if seconds in WINDOW_SECONDS else None


def feature_names(channels: Sequence[str]) -> tuple[str, ...]:
    return tuple(f"{channel}.{stat}" for channel in channels for stat in STATS)


@dataclass(frozen=True, slots=True)
class HistoryWindow:
    start: datetime
    end: datetime
    observations: tuple[ChannelObservation, ...]

    @property
    def position(self) -> int:
        """Windows of one stream are ordered by their end, in microseconds."""
        return int(self.end.timestamp() * 1_000_000)


def window_start(at: datetime, seconds: int) -> datetime:
    """Epoch-aligned, so the same instant always falls in the same window."""
    return _EPOCH + timedelta(seconds=int((at - _EPOCH).total_seconds() // seconds) * seconds)


def group_windows(
    observations: Iterable[ChannelObservation],
    *,
    seconds: int,
    measurement_point_id: str | None,
) -> list[HistoryWindow]:
    """Windows that hold at least one observation of this point, in time order."""
    grouped: dict[datetime, list[ChannelObservation]] = {}
    for item in observations:
        if item.measurement_point_id == measurement_point_id:
            grouped.setdefault(window_start(item.event_at, seconds), []).append(item)
    return [
        HistoryWindow(
            start,
            start + timedelta(seconds=seconds),
            tuple(sorted(items, key=lambda o: (o.channel_id, o.event_at))),
        )
        for start, items in sorted(grouped.items())
    ]


def _usable(item: ChannelObservation) -> bool:
    return (
        item.value is not None
        and math.isfinite(item.value)
        and item.source_quality_good
        and not item.conflicting
    )


def window_features(
    window: HistoryWindow, channels: Sequence[str]
) -> tuple[dict[str, float] | None, str | None]:
    """Mean, population standard deviation, minimum and maximum of each channel's good values."""
    by_channel: dict[str, list[float]] = {channel: [] for channel in channels}
    for item in window.observations:
        if item.channel_id in by_channel and _usable(item):
            by_channel[item.channel_id].append(float(item.value))  # type: ignore[arg-type]
    values: dict[str, float] = {}
    for channel in channels:
        series = np.asarray(by_channel[channel], dtype=float)
        if series.size < MIN_VALUES:
            return None, f"{channel}: {series.size} usable values, at least {MIN_VALUES} needed"
        values[f"{channel}.mean"] = float(series.mean())
        values[f"{channel}.std"] = float(series.std())
        values[f"{channel}.min"] = float(series.min())
        values[f"{channel}.max"] = float(series.max())
    return values, None


def window_digest(window: HistoryWindow, channels: Sequence[str]) -> str:
    """The exact values this window gave the model, so a later read can be compared."""
    rows = [
        [item.channel_id, item.event_at.isoformat(), item.value if _usable(item) else None]
        for item in window.observations
        if item.channel_id in channels
    ]
    return hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def prepare_history_step(
    window: HistoryWindow, spec: PackageInputSpec, *, binding: PhmBinding, snapshot_id: int
) -> PreparedStep:
    reference = {
        "kind": StepKind.HISTORY_WINDOW.value,
        "source_id": binding.source_id,
        "asset_id": binding.asset_id,
        "measurement_point_id": binding.measurement_point_id,
        "channels": list(spec.channels),
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "snapshot_id": snapshot_id,
        "input_digest": window_digest(window, spec.channels),
        "observation_count": len(window.observations),
    }
    seconds = window_seconds_of(spec.feature_set_id)
    features: tuple[float, ...] | None = None
    reason: str | None = None
    if spec.step_kind is not StepKind.HISTORY_WINDOW:
        reason = f"package expects {spec.step_kind.value} steps"
    elif seconds is None:
        reason = f"unsupported feature set for history windows: {spec.feature_set_id}"
    elif (window.end - window.start).total_seconds() != seconds:
        reason = "window length differs from the package"
    else:
        values, reason = window_features(window, spec.channels)
        if values is not None:
            missing = [name for name in spec.feature_names if name not in values]
            if missing:
                reason = f"features missing from step: {missing[:3]}"
            else:
                features = tuple(values[name] for name in spec.feature_names)
    return PreparedStep(
        step_key=f"history:{int(window.start.timestamp())}",
        position=window.position,
        replay=binding.recorded_replay,
        input_reference=reference,
        event_start=window.start,
        event_end=window.end,
        features=features,
        skip_reason=reason,
    )


def run_history_window_bindings(
    store: SqlitePhmAnalysisStore,
    history: HistoryReader,
    packages: PackageCache,
    *,
    page_windows: int = 200,
    max_spans: int = 24,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[BindingCycle, ...]:
    """Score each history-window binding's next complete windows, at most a page per cycle.

    A window is complete once the stream has a later observation; the window holding the latest
    stored value waits. Gaps without observations are passed over without a step.
    """
    cycles = []
    for binding in store.list_bindings():
        if binding.step_kind is not StepKind.HISTORY_WINDOW or packages.retired(binding.package_id):
            continue
        try:
            package = packages.get(binding.package_id)
        except ModelPackageError as error:
            store.set_binding_health(binding.binding_id, healthy=False, reason=str(error), at=now())
            cycles.append(BindingCycle(binding.binding_id, (), str(error)))
            continue
        spec = package.manifest.input
        seconds = window_seconds_of(spec.feature_set_id)
        if seconds is None:
            reason = f"unsupported feature set for history windows: {spec.feature_set_id}"
            store.set_binding_health(binding.binding_id, healthy=False, reason=reason, at=now())
            cycles.append(BindingCycle(binding.binding_id, (), reason))
            continue
        store.set_binding_health(binding.binding_id, healthy=True, reason=None, at=now())
        extent = history.history_channel_extent(binding.asset_id, spec.channels)
        if extent is None:
            continue
        progress = store.progress(binding.binding_id)
        start = (
            window_start(extent[0], seconds)
            if progress.cursor_position is None
            else datetime.fromtimestamp(progress.cursor_position / 1_000_000, tz=UTC)
        )
        complete_until = window_start(extent[1], seconds)
        snapshot = history.current_snapshot_id()
        windows: list[HistoryWindow] = []
        span_start, spans = start, 0
        while not windows and span_start < complete_until and spans < max_spans:
            span_end = min(complete_until, span_start + timedelta(seconds=seconds * page_windows))
            rows = history.query_channel_observations(
                binding.asset_id,
                source_id=binding.source_id,
                channel_ids=list(spec.channels),
                start_at=span_start,
                end_at=span_end,
                snapshot_id=snapshot,
            )
            windows = [
                window
                for window in group_windows(
                    rows, seconds=seconds, measurement_point_id=binding.measurement_point_id
                )
                if window.start >= span_start and window.end <= span_end
            ]
            span_start, spans = span_end, spans + 1
        steps = (
            prepare_history_step(window, spec, binding=binding, snapshot_id=snapshot)
            for window in windows
        )
        cycles.append(
            BindingCycle(binding.binding_id, run_binding(store, binding, package, steps, now=now))
        )
    return tuple(cycles)


@dataclass(frozen=True, slots=True)
class HistoryModelRequest:
    """What a person chose: whose record, which signals, which period to call usual."""

    asset_id: str
    source_id: str
    channels: tuple[str, ...]
    reference_start: datetime
    reference_end: datetime
    window_seconds: int
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.channels) <= MAX_CHANNELS or len(set(self.channels)) != len(
            self.channels
        ):
            raise ValueError(f"choose 1 to {MAX_CHANNELS} distinct signals")
        if self.window_seconds not in WINDOW_SECONDS:
            raise ValueError(f"window length must be one of {WINDOW_SECONDS} seconds")
        for at in (self.reference_start, self.reference_end):
            if at.utcoffset() is None:
                raise ValueError("reference period must be timezone-aware")
        if self.reference_end <= self.reference_start:
            raise ValueError("reference period must end after it starts")


@dataclass(frozen=True, slots=True)
class HistoryModelBuild:
    package_id: str | None
    reference_windows: int
    skipped_windows: int
    threshold: float | None = None
    reason: str | None = None
    reused: bool = False


def _reference_digest(reference: Sequence[tuple[float, ...]]) -> str:
    return hashlib.sha256(json.dumps(reference).encode()).hexdigest()


def _same_model(
    models_root: Path, request: HistoryModelRequest, digest: str, skipped: int
) -> HistoryModelBuild | None:
    """A package already built from these choices and the same reference values; pressing twice
    reuses it, while values changed inside the period (a later backfill) build a new one."""
    if not models_root.is_dir():
        return None
    wanted = {
        "dataset_id": request.source_id,
        "asset_ids": [request.asset_id],
        "measurement_point_id": request.measurement_point_id,
        "reference_start": request.reference_start.isoformat(),
        "reference_end": request.reference_end.isoformat(),
        "reference_digest": digest,
    }
    for path in sorted(models_root.glob("*/package.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        if not isinstance(body, dict) or body.get("recipe_id") != RECIPE_ID:
            continue
        scope, spec = body.get("training_scope") or {}, body.get("input") or {}
        if (
            spec.get("channels") == list(request.channels)
            and spec.get("feature_set_id") == feature_set_id(request.window_seconds)
            and all(scope.get(key) == value for key, value in wanted.items())
        ):
            return HistoryModelBuild(
                str(body["package_id"]),
                int(scope.get("reference_windows") or 0),
                skipped,
                (body.get("output") or {}).get("threshold"),
                reused=True,
            )
    return None


def build_history_model(
    models_root: Path,
    history: HistoryReader,
    request: HistoryModelRequest,
    *,
    created_at: datetime,
    code_revision: str,
) -> HistoryModelBuild:
    """Fit an Isolation Forest on the reference windows, or say why the period is too thin."""
    seconds = request.window_seconds
    snapshot = history.current_snapshot_id()
    start = window_start(request.reference_start, seconds)
    rows = history.query_channel_observations(
        request.asset_id,
        source_id=request.source_id,
        channel_ids=list(request.channels),
        start_at=start,
        end_at=request.reference_end,
        snapshot_id=snapshot,
    )
    reference: list[tuple[float, ...]] = []
    skipped = 0
    names = feature_names(request.channels)
    for window in group_windows(
        rows, seconds=seconds, measurement_point_id=request.measurement_point_id
    ):
        if window.start < start or window.end > request.reference_end:
            continue
        values, _ = window_features(window, request.channels)
        if values is None:
            skipped += 1
        else:
            reference.append(tuple(values[name] for name in names))
    if len(reference) < MIN_REFERENCE_WINDOWS:
        return HistoryModelBuild(
            None,
            len(reference),
            skipped,
            reason=f"기준 기간에서 쓸 수 있는 구간이 {len(reference)}개입니다. "
            f"최소 {MIN_REFERENCE_WINDOWS}개가 필요하니 기간을 늘리거나 구간 길이를 줄이세요.",
        )
    digest = _reference_digest(reference)
    if (existing := _same_model(models_root, request, digest, skipped)) is not None:
        return existing
    array = np.asarray(reference)
    center = np.median(array, axis=0)
    spread = np.quantile(array, 0.75, axis=0) - np.quantile(array, 0.25, axis=0)
    scale = np.maximum(spread, 1e-6 * np.maximum(1.0, np.abs(center)))
    preprocessing = AffinePreprocessing(center.tolist(), scale.tolist())
    build = PackageBuild(
        recipe_id=RECIPE_ID,
        estimator_kind=EstimatorKind.ISOLATION_FOREST_REFIT,
        input=PackageInputSpec(
            StepKind.HISTORY_WINDOW, request.channels, feature_set_id(seconds), names
        ),
        output=PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="anomaly-score",
            threshold=0,
            threshold_rule=f"operator-reference-quantile-{THRESHOLD_QUANTILE}",
            review_interval=ReviewIntervalRule(2, 1),
            step_period_seconds=seconds,
        ),
        preprocessing=preprocessing,
        estimator_state={
            "n_estimators": 100,
            "max_samples": min(256, len(reference)),
            "contamination": "auto",
            "max_features": 1.0,
            "bootstrap": False,
            "random_seed": 42,
        },
        fit_rows=preprocessing.transform(reference),
        probe_rows=reference[:8],
        training_scope=_scope(request, snapshot, len(reference), digest),
        validation={"evidence_class": "operator-reference-not-validated"},
        applicability={"source_id": [request.source_id], "asset_id": [request.asset_id]},
        created_at=created_at.isoformat(),
        code_revision=code_revision,
    )
    # The threshold is a reference-score quantile, so score the reference with a provisional copy.
    models_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".history-model-", dir=models_root) as temporary:
        provisional = write_model_package(Path(temporary), build)
        scores = load_model_package(Path(temporary) / provisional.package_id).evaluate(reference)
    threshold = float(np.quantile(scores, THRESHOLD_QUANTILE))
    final = replace(build, output=replace(build.output, threshold=threshold))
    manifest = write_model_package(models_root, final)
    return HistoryModelBuild(manifest.package_id, len(reference), skipped, threshold)


def _scope(
    request: HistoryModelRequest, snapshot: int, windows: int, digest: str
) -> Mapping[str, Any]:
    return {
        "dataset_id": request.source_id,
        "partition": "operator-reference",
        "asset_ids": [request.asset_id],
        "measurement_point_id": request.measurement_point_id,
        "reference_start": request.reference_start.isoformat(),
        "reference_end": request.reference_end.isoformat(),
        "snapshot_id": snapshot,
        "reference_windows": windows,
        "reference_digest": digest,
    }


def project_history_window(
    store: SqlitePhmAnalysisStore, history: HistoryReader, *, binding_id: str, position: int
) -> dict[str, Any]:
    """The exact stored values one scored window used, re-read at its recorded snapshot.

    A different digest means the stored record changed after the step; the values are then not
    shown as the model's input.
    """
    binding = next((b for b in store.list_bindings() if b.binding_id == binding_id), None)
    if binding is None or binding.step_kind is not StepKind.HISTORY_WINDOW:
        return {"available": False, "reason": "history window binding unavailable"}
    result = store.get_result(binding_id, position)
    if result is None:
        return {"available": False, "reason": "step not analyzed"}
    reference = result.input_reference
    try:
        start = datetime.fromisoformat(str(reference["window_start"]))
        end = datetime.fromisoformat(str(reference["window_end"]))
        snapshot = int(reference["snapshot_id"])
        channels = [str(c) for c in reference["channels"]]
    except KeyError, TypeError, ValueError:
        return {"available": False, "reason": "stored window reference unreadable"}
    if not channels:
        return {"available": False, "reason": "stored window reference unreadable"}
    rows = history.query_channel_observations(
        binding.asset_id,
        source_id=binding.source_id,
        channel_ids=channels,
        start_at=start,
        end_at=end,
        snapshot_id=snapshot,
    )
    windows = [
        w
        for w in group_windows(
            rows,
            seconds=int((end - start).total_seconds()),
            measurement_point_id=binding.measurement_point_id,
        )
        if w.start == start
    ]
    if not windows:
        return {"available": False, "reason": "stored window values unavailable"}
    window = windows[0]
    if window_digest(window, channels) != reference.get("input_digest"):
        return {"available": False, "reason": "stored values changed after this window was scored"}
    preview = []
    for channel in channels:
        items = [o for o in window.observations if o.channel_id == channel]
        if not items:
            continue
        preview.append(
            {
                "channel_id": channel,
                "unit": items[0].unit,
                "observed_property": items[0].observed_property,
                "scope": items[0].scope,
                "points": [
                    {
                        "at": o.event_at.isoformat(),
                        "value": o.value if _usable(o) else None,
                        "quality": "conflict"
                        if o.conflicting
                        else ("good" if _usable(o) else "unusable"),
                    }
                    for o in items
                ],
            }
        )
    return {
        "schema_version": 1,
        "available": True,
        "binding_id": binding_id,
        "position": position,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "snapshot_id": snapshot,
        "measurement_point_id": binding.measurement_point_id,
        "channels": preview,
    }
