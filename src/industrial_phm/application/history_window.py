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
from bisect import bisect_right
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
# A stream that records a current: one forest per operating level of that current (ADR-0034).
LEVEL_RECIPE_ID = "operator-history-iforest-by-level-v1"
THRESHOLD_QUANTILE = 0.995
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class HistoryReader(Protocol):
    def current_snapshot_id(self) -> int: ...

    def history_stream_extent(
        self,
        asset_id: str,
        *,
        source_id: str,
        measurement_point_id: str | None,
        channel_ids: Sequence[str],
        after: datetime | None,
        snapshot_id: int,
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


Meaning = tuple[str | None, str | None, str | None, str | None]


def _meaning(item: ChannelObservation) -> Meaning:
    return (item.observed_property, item.scope, item.unit, item.semantic_version)


def channel_meanings(
    window: HistoryWindow, channels: Sequence[str]
) -> tuple[dict[str, Meaning], str | None]:
    """The one property, scope, unit and semantic version of each channel's good values here.

    Values recorded with different units or meanings are not one feature; such a window is a skip.
    """
    found: dict[str, set[Meaning]] = {channel: set() for channel in channels}
    for item in window.observations:
        if item.channel_id in found and _usable(item):
            found[item.channel_id].add(_meaning(item))
    for channel, kinds in found.items():
        if len(kinds) > 1:
            return {}, f"{channel}: values with different units or meanings in one window"
    return {channel: next(iter(kinds)) for channel, kinds in found.items() if kinds}, None


def _say(meaning: Sequence[str | None]) -> str:
    return "/".join(part or "-" for part in meaning[:3])


def window_features(
    window: HistoryWindow,
    channels: Sequence[str],
    reference: Mapping[str, Sequence[str | None]] | None = None,
) -> tuple[dict[str, float] | None, str | None]:
    """Mean, population standard deviation, minimum and maximum of each channel's good values.

    With `reference` (what the model learned), a channel recorded with another unit or meaning
    is a skip rather than a comparable feature.
    """
    meanings, reason = channel_meanings(window, channels)
    if reason is not None:
        return None, reason
    for channel, meaning in meanings.items():
        learned = None if reference is None else reference.get(channel)
        if learned is not None and tuple(learned) != meaning:
            return None, (
                f"{channel}: unit or meaning differs from the reference period "
                f"({_say(learned)} -> {_say(meaning)})"
            )
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
    window: HistoryWindow,
    spec: PackageInputSpec,
    *,
    binding: PhmBinding,
    snapshot_id: int,
    learned: Mapping[str, Sequence[str | None]] | None = None,
) -> PreparedStep:
    """One window as a model step; `learned` is the unit and meaning per channel the model saw."""
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
        values, reason = window_features(window, spec.channels, learned)
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
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[BindingCycle, ...]:
    """Score each history-window binding's next complete windows, at most a page per cycle.

    Progress is judged by the same (source, point, channels) stream the steps read, at the same
    snapshot: a window is complete once that stream has a later observation, and the next page
    starts at its first observation after the cursor, so a gap of any length is passed over.
    """
    cycles = []
    for binding in store.list_bindings():
        if binding.step_kind is not StepKind.HISTORY_WINDOW:
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
        cursor = store.progress(binding.binding_id).cursor_position
        snapshot = history.current_snapshot_id()
        extent = history.history_stream_extent(
            binding.asset_id,
            source_id=binding.source_id,
            measurement_point_id=binding.measurement_point_id,
            channel_ids=list(spec.channels),
            after=None if cursor is None else datetime.fromtimestamp(cursor / 1_000_000, tz=UTC),
            snapshot_id=snapshot,
        )
        windows: list[HistoryWindow] = []
        if extent is not None:
            start, complete_until = (
                window_start(extent[0], seconds),
                window_start(extent[1], seconds),
            )
            end = min(complete_until, start + timedelta(seconds=seconds * page_windows))
            if start < end:
                rows = history.query_channel_observations(
                    binding.asset_id,
                    source_id=binding.source_id,
                    channel_ids=list(spec.channels),
                    start_at=start,
                    end_at=end,
                    snapshot_id=snapshot,
                )
                windows = [
                    window
                    for window in group_windows(
                        rows, seconds=seconds, measurement_point_id=binding.measurement_point_id
                    )
                    if window.end <= end
                ]
        learned = package.manifest.training_scope.get("channel_meanings")
        steps = (
            prepare_history_step(
                window,
                spec,
                binding=binding,
                snapshot_id=snapshot,
                learned=learned if isinstance(learned, Mapping) else None,
            )
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
class LevelBasis:
    """The current that says how the equipment ran, and its operating levels frozen at build.

    Band 0 is stopped (below ``edges[0]``); band ``k`` runs from ``edges[k - 1]`` and usually
    draws ``typical[k - 1]``, as in ``operating_state.OperatingLevels``.
    """

    channel: str
    edges: tuple[float, ...]
    typical: tuple[float, ...]

    def band(self, current: float) -> int:
        return bisect_right(self.edges, current)

    def name(self, band: int) -> str:
        """'stopped' or '11 A': the level as the screens' '약 11 A 운전' names it."""
        if band == 0:
            return "stopped"
        value = float(f"{self.typical[band - 1]:.2g}")
        return (f"{value:,.0f}" if abs(value) >= 10 else f"{value:g}") + " A"


@dataclass(frozen=True, slots=True)
class HistoryModelBuild:
    package_id: str | None
    reference_windows: int
    skipped_windows: int
    threshold: float | None = None
    reason: str | None = None
    reused: bool = False
    # Reference windows per operating level and which levels the model learned (level models).
    levels: Mapping[str, Any] | None = None


def _reference_digest(reference: Sequence[tuple[float, ...]]) -> str:
    return hashlib.sha256(json.dumps(reference).encode()).hexdigest()


def _same_model(
    models_root: Path,
    recipe: str,
    channels: Sequence[str],
    feature_set: str,
    wanted: Mapping[str, Any],
    skipped: int,
) -> HistoryModelBuild | None:
    """A package already built from these choices and the same reference values; pressing twice
    reuses it, while values changed inside the period (a later backfill) build a new one."""
    if not models_root.is_dir():
        return None
    for path in sorted(models_root.glob("*/package.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        if not isinstance(body, dict) or body.get("recipe_id") != recipe:
            continue
        scope, spec = body.get("training_scope") or {}, body.get("input") or {}
        if (
            spec.get("channels") == list(channels)
            and spec.get("feature_set_id") == feature_set
            and all(scope.get(key) == value for key, value in wanted.items())
        ):
            return HistoryModelBuild(
                str(body["package_id"]),
                int(scope.get("reference_windows") or 0),
                skipped,
                (body.get("output") or {}).get("threshold"),
                reused=True,
                levels=scope.get("operating_levels"),
            )
    return None


def build_history_model(
    models_root: Path,
    history: HistoryReader,
    request: HistoryModelRequest,
    *,
    created_at: datetime,
    code_revision: str,
    levels: LevelBasis | None = None,
) -> HistoryModelBuild:
    """Fit Isolation Forest on the reference windows, or say why the period is too thin.

    With ``levels`` (the stream records a current) each operating level is learned and judged
    apart; without, one forest learns the whole period.
    """
    seconds = request.window_seconds
    snapshot = history.current_snapshot_id()
    start = window_start(request.reference_start, seconds)
    # 운전 수준을 정하는 전류가 고른 신호에 없으면 입력에 더한다: 구간마다 그 수준을 읽어야 한다.
    channels = (
        request.channels
        if levels is None or levels.channel in request.channels
        else (*request.channels, levels.channel)
    )
    rows = history.query_channel_observations(
        request.asset_id,
        source_id=request.source_id,
        channel_ids=list(channels),
        start_at=start,
        end_at=request.reference_end,
        snapshot_id=snapshot,
    )
    reference: list[tuple[float, ...]] = []
    meanings: dict[str, set[Meaning]] = {channel: set() for channel in channels}
    skipped = 0
    names = feature_names(channels)
    # 구간이 빠졌어도 값이 있었던 신호: 값이 하나도 없는 신호를 이름으로 말하려고 센다.
    seen: set[str] = set()
    for window in group_windows(
        rows, seconds=seconds, measurement_point_id=request.measurement_point_id
    ):
        if window.start < start or window.end > request.reference_end:
            continue
        seen.update(channel_meanings(window, channels)[0])
        values, _ = window_features(window, channels)
        if values is None:
            skipped += 1
        else:
            reference.append(tuple(values[name] for name in names))
            for channel, meaning in channel_meanings(window, channels)[0].items():
                meanings[channel].add(meaning)
    changed = [channel for channel, kinds in meanings.items() if len(kinds) > 1]
    if changed:
        return HistoryModelBuild(
            None,
            len(reference),
            skipped,
            reason=f"기준 기간 안에서 {', '.join(changed)} 신호의 단위나 의미가 바뀝니다. "
            "바뀌기 전이나 후로 기간을 좁히세요.",
        )
    learned = {channel: list(next(iter(kinds))) for channel, kinds in meanings.items() if kinds}
    # 기준 기간에 값이 하나도 없는 신호가 있으면 모든 구간이 빠진다.
    # 기간이 아니라 그 신호가 원인이다.
    silent = [channel for channel in channels if channel not in seen]
    if silent and len(reference) < MIN_REFERENCE_WINDOWS:
        return HistoryModelBuild(
            None,
            len(reference),
            skipped,
            reason=f"{', '.join(silent)} 신호는 기준 기간에 값이 없습니다. "
            "이 신호를 빼거나 값이 있는 기간을 고르세요.",
        )
    if len(reference) < MIN_REFERENCE_WINDOWS:
        return HistoryModelBuild(
            None,
            len(reference),
            skipped,
            reason=f"기준 기간에서 쓸 수 있는 구간이 {len(reference)}개입니다. "
            f"최소 {MIN_REFERENCE_WINDOWS}개가 필요하니 기간을 늘리거나 구간 길이를 줄이세요.",
        )
    digest = _reference_digest(reference)
    scope = _scope(request, snapshot, len(reference), digest, learned)
    if levels is not None:
        return _build_by_level(
            models_root,
            request,
            channels,
            reference,
            skipped,
            levels,
            scope,
            created_at=created_at,
            code_revision=code_revision,
        )
    wanted = {key: scope[key] for key in _REUSE_KEYS}
    if (
        existing := _same_model(
            models_root, RECIPE_ID, channels, feature_set_id(seconds), wanted, skipped
        )
    ) is not None:
        return existing
    array = np.asarray(reference)
    center = np.median(array, axis=0)
    spread = np.quantile(array, 0.75, axis=0) - np.quantile(array, 0.25, axis=0)
    scale = np.maximum(spread, 1e-6 * np.maximum(1.0, np.abs(center)))
    preprocessing = AffinePreprocessing(center.tolist(), scale.tolist())
    build = PackageBuild(
        recipe_id=RECIPE_ID,
        estimator_kind=EstimatorKind.ISOLATION_FOREST_REFIT,
        input=PackageInputSpec(StepKind.HISTORY_WINDOW, channels, feature_set_id(seconds), names),
        output=_output(seconds, f"operator-reference-quantile-{THRESHOLD_QUANTILE}"),
        preprocessing=preprocessing,
        estimator_state={**_FOREST, "max_samples": min(256, len(reference))},
        fit_rows=preprocessing.transform(reference),
        probe_rows=reference[:8],
        training_scope=scope,
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


# The deterministic refit every operator-built forest uses; max_samples follows the rows.
_FOREST: dict[str, Any] = {
    "n_estimators": 100,
    "contamination": "auto",
    "max_features": 1.0,
    "bootstrap": False,
    "random_seed": 42,
}
_REUSE_KEYS = (
    "dataset_id",
    "asset_ids",
    "measurement_point_id",
    "reference_start",
    "reference_end",
    "reference_digest",
    "channel_meanings",
)


def _output(seconds: int, rule: str, threshold: float = 0) -> PackageOutputSpec:
    return PackageOutputSpec(
        task=ModelTask.ANOMALY_SCORE,
        value_name="anomaly-score",
        threshold=threshold,
        threshold_rule=rule,
        review_interval=ReviewIntervalRule(2, 1),
        step_period_seconds=seconds,
    )


def _build_by_level(
    models_root: Path,
    request: HistoryModelRequest,
    channels: Sequence[str],
    reference: Sequence[tuple[float, ...]],
    skipped: int,
    levels: LevelBasis,
    scope: Mapping[str, Any],
    *,
    created_at: datetime,
    code_revision: str,
) -> HistoryModelBuild:
    """One forest per operating level the reference period held enough windows of.

    Each level gets its own scaling (median, IQR) and its own threshold at the 99.5th percentile
    of that level's reference scores, so a window is compared only with windows of its own load.
    A level with fewer than the minimum windows is not learned and its windows are not judged.
    """
    seconds = request.window_seconds
    names = feature_names(channels)
    index = names.index(f"{levels.channel}.mean")
    bands = [levels.band(row[index]) for row in reference]
    # 기록의 모든 운전 수준을 센다(기준 기간에 없던 수준은 0개): 판정하지 않을 수준을 말해야 한다.
    # 정지는 기준 기간에 있었을 때만 센다(한 번도 멈추지 않은 설비에 '정지'를 말하지 않는다).
    running = range(1, len(levels.edges) + 1)
    counts = {band: bands.count(band) for band in sorted({*running, *bands})}
    learned = [band for band, count in counts.items() if count >= MIN_REFERENCE_WINDOWS]
    operating = {
        "channel": levels.channel,
        # 사람이 고르지 않았는데 수준을 읽으려고 더한 전류인지: 화면의 '신호 N개'는 고른 것만 센다.
        "added": levels.channel not in request.channels,
        "edges": list(levels.edges),
        "typical": list(levels.typical),
        "reference_windows": {str(band): count for band, count in counts.items()},
        "learned": [str(band) for band in learned],
    }
    if not learned:
        said = ", ".join(f"{_said(levels, band)} {count}개" for band, count in counts.items())
        return HistoryModelBuild(
            None,
            len(reference),
            skipped,
            reason=f"운전 수준별로 학습하려면 한 수준에 구간이 {MIN_REFERENCE_WINDOWS}개 이상 "
            f"있어야 합니다. 기준 기간에는 {said}입니다. 기간을 늘리세요.",
            levels=operating,
        )
    scope = {**scope, "operating_levels": operating}
    wanted = {key: scope[key] for key in (*_REUSE_KEYS, "operating_levels")}
    if (
        existing := _same_model(
            models_root, LEVEL_RECIPE_ID, channels, feature_set_id(seconds), wanted, skipped
        )
    ) is not None:
        return existing
    rows = [row for row, band in zip(reference, bands, strict=True) if band in learned]
    row_bands = [band for band in bands if band in learned]
    state: dict[str, Any] = {
        **_FOREST,
        "level_feature": f"{levels.channel}.mean",
        "level_index": index,
        "level_edges": list(levels.edges),
        "level_names": [levels.name(band) for band in range(len(levels.edges) + 1)],
        "levels": {},
    }
    for band in learned:
        array = np.asarray([row for row, own in zip(rows, row_bands, strict=True) if own == band])
        center = np.median(array, axis=0)
        spread = np.quantile(array, 0.75, axis=0) - np.quantile(array, 0.25, axis=0)
        scale = np.maximum(spread, 1e-6 * np.maximum(1.0, np.abs(center)))
        state["levels"][str(band)] = {
            "center": center.tolist(),
            "scale": scale.tolist(),
            "threshold": 1.0,
            "max_samples": min(256, len(array)),
        }
    # The package scales inside each level, so its own preprocessing is the identity.
    identity = AffinePreprocessing([0.0] * len(names), [1.0] * len(names))
    # A probe row from every learned level, so loading checks each forest.
    first = {band: rows[row_bands.index(band)] for band in learned}
    probe = [first[band] for band in learned]
    build = PackageBuild(
        recipe_id=LEVEL_RECIPE_ID,
        estimator_kind=EstimatorKind.ISOLATION_FOREST_BY_LEVEL,
        input=PackageInputSpec(StepKind.HISTORY_WINDOW, channels, feature_set_id(seconds), names),
        output=_output(seconds, f"operator-reference-quantile-{THRESHOLD_QUANTILE}-per-level"),
        preprocessing=identity,
        estimator_state=state,
        fit_rows=rows,
        fit_levels=row_bands,
        probe_rows=(probe + rows)[:8],
        training_scope=scope,
        validation={"evidence_class": "operator-reference-not-validated"},
        applicability={"source_id": [request.source_id], "asset_id": [request.asset_id]},
        created_at=created_at.isoformat(),
        code_revision=code_revision,
    )
    # Each level's threshold is a quantile of its own reference scores: score with a provisional
    # copy whose thresholds are 1, then fix each level's.
    models_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".history-model-", dir=models_root) as temporary:
        provisional = write_model_package(Path(temporary), build)
        scores = load_model_package(Path(temporary) / provisional.package_id).evaluate(rows)
    for band in learned:
        own = [score for score, b in zip(scores, row_bands, strict=True) if b == band]
        state["levels"][str(band)]["threshold"] = float(np.quantile(own, THRESHOLD_QUANTILE))
    final = replace(build, estimator_state=state, output=replace(build.output, threshold=1.0))
    manifest = write_model_package(models_root, final)
    return HistoryModelBuild(manifest.package_id, len(reference), skipped, 1.0, levels=operating)


def _said(levels: LevelBasis, band: int) -> str:
    name = levels.name(band)
    return "정지" if name == "stopped" else f"약 {name} 운전"


def _scope(
    request: HistoryModelRequest,
    snapshot: int,
    windows: int,
    digest: str,
    learned: Mapping[str, list[str | None]],
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
        "channel_meanings": dict(learned),
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
