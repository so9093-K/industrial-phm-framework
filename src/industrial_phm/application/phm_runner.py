"""Drive PHM bindings from their step sources (ADR-0025).

The runner turns each new acquisition snapshot or finalized observation window into a step
projected onto the bound package's input schema, then commits it through
:class:`SqlitePhmAnalysisStore`. A package that cannot be loaded marks only its binding
unavailable; other bindings keep running.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
    read_snapshot_waveform,
)
from industrial_phm.application.analysis_input import (
    window_channel_observations,
    window_input_reference,
)
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_CHANNELS,
    ELECTRICAL_WINDOW_FEATURE_SET_ID,
    align_electrical_samples,
    electrical_window_features,
    resolve_electrical_roles,
)
from industrial_phm.application.observation_window import DurableObservationWindow
from industrial_phm.application.phm_analysis import (
    PhmBinding,
    PreparedStep,
    SqlitePhmAnalysisStore,
    StepResult,
    run_binding,
)
from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.features.vibration import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureError,
    extract_vibration_features,
)
from industrial_phm.models.package import (
    LoadedModelPackage,
    ModelPackageError,
    PackageInputSpec,
    StepKind,
    is_retired_package,
    load_model_package,
)

_SnapshotFeatures = Callable[[CanonicalTimeSeries], Mapping[str, float]]


def _vibration_statistical(series: CanonicalTimeSeries) -> Mapping[str, float]:
    vector = extract_vibration_features(series)
    return dict(zip(vector.feature_names, vector.values, strict=True))


SNAPSHOT_FEATURE_SETS: Mapping[str, _SnapshotFeatures] = {
    VIBRATION_STATISTICAL_FEATURE_SET_ID: _vibration_statistical,
}


FeatureMemo = dict[tuple[str, str], Mapping[str, float] | str]


def prepare_snapshot_step(
    snapshot: AcquisitionSnapshot,
    spec: PackageInputSpec,
    memo: FeatureMemo | None = None,
    *,
    recorded_replay: bool = False,
) -> PreparedStep:
    """Project one snapshot onto the package input schema, or record why it does not fit."""
    reference = {
        "kind": StepKind.ACQUISITION_SNAPSHOT.value,
        "source_id": snapshot.source_id,
        "asset_id": snapshot.asset_id,
        "ordinal": snapshot.ordinal,
        "sha256": snapshot.sha256,
        "file_name": snapshot.file_path.name,
        "delivered_at": snapshot.delivered_at.isoformat(),
    }
    context = {key: str(value) for key, value in snapshot.metadata.items() if value is not None}
    context["recorded_replay"] = "true" if snapshot.replay or recorded_replay else "false"
    features, reason = _snapshot_features(snapshot, spec, {} if memo is None else memo)
    return PreparedStep(
        step_key=snapshot.step_key,
        position=snapshot.ordinal,
        replay=snapshot.replay or recorded_replay,
        input_reference=reference,
        event_start=snapshot.event_at,
        features=features,
        context=context,
        skip_reason=reason,
    )


def _snapshot_features(
    snapshot: AcquisitionSnapshot, spec: PackageInputSpec, memo: FeatureMemo
) -> tuple[tuple[float, ...] | None, str | None]:
    reason = _snapshot_incompatibility(snapshot, spec)
    if reason is not None:
        return None, reason
    extractor = SNAPSHOT_FEATURE_SETS.get(spec.feature_set_id)
    if extractor is None:
        return None, f"unsupported feature set for snapshots: {spec.feature_set_id}"
    # Bindings sharing a stream read the same verified bytes; extract each snapshot once.
    key = (snapshot.sha256, spec.feature_set_id)
    if key not in memo:
        try:
            memo[key] = extractor(read_snapshot_waveform(snapshot))
        except (AcquisitionSnapshotError, VibrationFeatureError, ValueError) as error:
            memo[key] = f"snapshot unreadable: {error}"
    cached = memo[key]
    if isinstance(cached, str):
        return None, cached
    missing = [name for name in spec.feature_names if name not in cached]
    if missing:
        return None, f"features missing from step: {missing[:3]}"
    return tuple(cached[name] for name in spec.feature_names), None


def _snapshot_incompatibility(snapshot: AcquisitionSnapshot, spec: PackageInputSpec) -> str | None:
    if spec.step_kind is not StepKind.ACQUISITION_SNAPSHOT:
        return f"package expects {spec.step_kind.value} steps"
    if tuple(snapshot.channels) != tuple(spec.channels):
        return (
            f"channels differ from the package input: got {list(snapshot.channels)}, "
            f"expected {list(spec.channels)}"
        )
    if spec.sampling_rate_hz is not None and snapshot.sampling_rate_hz != spec.sampling_rate_hz:
        return (
            f"sampling rate {snapshot.sampling_rate_hz} Hz differs from {spec.sampling_rate_hz} Hz"
        )
    if spec.samples_per_step is not None and snapshot.sample_count != spec.samples_per_step:
        return f"sample count {snapshot.sample_count} differs from {spec.samples_per_step}"
    return None


@dataclass(frozen=True, slots=True)
class BindingCycle:
    binding_id: str
    results: Sequence[StepResult]
    error: str | None = None


class PackageCache:
    """Load each package once per runner process; remember failures until the next cycle."""

    def __init__(self, models_root: Path) -> None:
        self._root = models_root
        self._loaded: dict[str, LoadedModelPackage] = {}
        self._retired: dict[str, bool] = {}

    def retired(self, package_id: str) -> bool:
        """Whether the package declares a task this product no longer runs (left untouched)."""
        if package_id not in self._retired:
            self._retired[package_id] = is_retired_package(self._root, package_id)
        return self._retired[package_id]

    def get(self, package_id: str) -> LoadedModelPackage:
        package = self._loaded.get(package_id)
        if package is None:
            if "/" in package_id or package_id.startswith("."):
                raise ModelPackageError("invalid package ID")
            package = load_model_package(self._root / package_id)
            self._loaded[package_id] = package
        return package


def run_snapshot_bindings(
    store: SqlitePhmAnalysisStore,
    snapshots: SqliteAcquisitionSnapshotRepository,
    packages: PackageCache,
    *,
    page_size: int = 200,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[BindingCycle, ...]:
    """Process up to ``page_size`` new snapshots for every snapshot binding."""
    cycles = []
    memo: FeatureMemo = {}
    for binding in store.list_bindings():
        if binding.step_kind is not StepKind.ACQUISITION_SNAPSHOT or packages.retired(
            binding.package_id
        ):
            continue
        cycles.append(_run_one(store, snapshots, packages, binding, page_size, now, memo))
    return tuple(cycles)


def _run_one(
    store: SqlitePhmAnalysisStore,
    snapshots: SqliteAcquisitionSnapshotRepository,
    packages: PackageCache,
    binding: PhmBinding,
    page_size: int,
    now: Callable[[], datetime],
    memo: FeatureMemo,
) -> BindingCycle:
    try:
        package = packages.get(binding.package_id)
    except ModelPackageError as error:
        store.set_binding_health(binding.binding_id, healthy=False, reason=str(error), at=now())
        return BindingCycle(binding.binding_id, (), str(error))
    store.set_binding_health(binding.binding_id, healthy=True, reason=None, at=now())
    progress = store.progress(binding.binding_id)
    pending = snapshots.list_after(
        binding.source_id,
        binding.asset_id,
        after_ordinal=progress.cursor_position,
        limit=page_size,
    )
    spec = package.manifest.input
    steps = (
        prepare_snapshot_step(snapshot, spec, memo, recorded_replay=binding.recorded_replay)
        for snapshot in pending
    )
    return BindingCycle(binding.binding_id, run_binding(store, binding, package, steps, now=now))


# Observation windows ------------------------------------------------------------

_WindowFeatures = Callable[
    [DurableObservationWindow], tuple[Mapping[str, float] | None, str | None]
]


def _electrical_window(
    window: DurableObservationWindow,
) -> tuple[Mapping[str, float] | None, str | None]:
    if (window.window_end - window.window_start).total_seconds() != 300:
        return None, "electrical-window-v1 requires a 300-second finalized window"
    observations = window_channel_observations(window)
    roles, reason = resolve_electrical_roles(observations)
    if roles is None:
        return None, reason
    samples, excluded = align_electrical_samples(observations, roles)
    features, reason, _ = electrical_window_features(samples)
    if reason is not None and excluded:
        reason += (
            " (excluded times: " + ", ".join(f"{k}={v}" for k, v in sorted(excluded.items())) + ")"
        )
    return features, reason


WINDOW_FEATURE_SETS: Mapping[str, tuple[tuple[str, ...], _WindowFeatures]] = {
    ELECTRICAL_WINDOW_FEATURE_SET_ID: (ELECTRICAL_WINDOW_CHANNELS, _electrical_window),
}


def window_position(window: DurableObservationWindow) -> int:
    """Order windows of one stream by their event-time end, in microseconds."""
    return int(window.window_end.timestamp() * 1_000_000)


def prepare_window_step(
    window: DurableObservationWindow, spec: PackageInputSpec, *, recorded_replay: bool
) -> PreparedStep:
    """Project one finalized window (ADR-0008 accepted events) onto the package schema."""
    reference = window_input_reference(window)
    input_reference = {
        "kind": StepKind.OBSERVATION_WINDOW.value,
        "window_id": window.window_id,
        "source_id": window.source_id,
        "asset_id": window.asset_id,
        "measurement_point_id": window.measurement_point_id,
        "window_start": window.window_start.isoformat(),
        "window_end": window.window_end.isoformat(),
        "input_digest": reference.input_digest,
        "accepted_event_count": window.accepted_event_count,
    }
    features: tuple[float, ...] | None = None
    reason: str | None = None
    if spec.step_kind is not StepKind.OBSERVATION_WINDOW:
        reason = f"package expects {spec.step_kind.value} steps"
    elif (feature_set := WINDOW_FEATURE_SETS.get(spec.feature_set_id)) is None:
        reason = f"unsupported feature set for windows: {spec.feature_set_id}"
    elif tuple(spec.channels) != feature_set[0]:
        reason = f"channels differ from feature set {spec.feature_set_id}: {list(spec.channels)}"
    elif spec.sampling_rate_hz is not None or spec.samples_per_step is not None:
        reason = "fixed sampling rate or sample count cannot be verified for finalized windows"
    else:
        values, reason = feature_set[1](window)
        if values is not None:
            missing = [name for name in spec.feature_names if name not in values]
            if missing:
                reason = f"features missing from step: {missing[:3]}"
            else:
                features = tuple(values[name] for name in spec.feature_names)
    return PreparedStep(
        step_key=f"window:{window.window_id}",
        position=window_position(window),
        replay=recorded_replay,
        input_reference=input_reference,
        event_start=window.window_start,
        event_end=window.window_end,
        features=features,
        context={
            "asset_id": window.asset_id,
            "recorded_replay": "true" if recorded_replay else "false",
        },
        skip_reason=None if features is not None else (reason or "window not evaluated"),
    )


class WindowReader(Protocol):
    def list_windows_after(
        self,
        *,
        after_window_end: datetime | None = None,
        after_window_id: str | None = None,
        limit: int = 1000,
        source_id: str | None = None,
        asset_id: str | None = None,
        measurement_point_id: str | None = None,
    ) -> tuple[DurableObservationWindow, ...]: ...


def run_window_bindings(
    store: SqlitePhmAnalysisStore,
    windows: WindowReader,
    packages: PackageCache,
    *,
    page_size: int = 200,
    max_scanned: int = 5_000,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[BindingCycle, ...]:
    """Process new finalized windows of each window binding's (source, asset) stream."""
    cycles = []
    for binding in store.list_bindings():
        if binding.step_kind is not StepKind.OBSERVATION_WINDOW or packages.retired(
            binding.package_id
        ):
            continue
        try:
            package = packages.get(binding.package_id)
        except ModelPackageError as error:
            store.set_binding_health(binding.binding_id, healthy=False, reason=str(error), at=now())
            cycles.append(BindingCycle(binding.binding_id, (), str(error)))
            continue
        store.set_binding_health(binding.binding_id, healthy=True, reason=None, at=now())
        progress = store.progress(binding.binding_id)
        after_end = (
            None
            if progress.cursor_position is None
            else datetime.fromtimestamp(progress.cursor_position / 1_000_000, tz=UTC)
        )
        after_id = (progress.cursor_step_key or "").removeprefix("window:") or None
        pending: list[DurableObservationWindow] = []
        scanned = 0
        while len(pending) < page_size and scanned < max_scanned:
            page = windows.list_windows_after(
                after_window_end=after_end,
                after_window_id=after_id,
                limit=500,
                source_id=binding.source_id,
                asset_id=binding.asset_id,
                measurement_point_id=binding.measurement_point_id,
            )
            if not page:
                break
            scanned += len(page)
            pending.extend(
                w
                for w in page
                if (w.source_id, w.asset_id, w.measurement_point_id)
                == (binding.source_id, binding.asset_id, binding.measurement_point_id)
            )
            after_end, after_id = page[-1].window_end, page[-1].window_id
        spec = package.manifest.input
        steps = (
            prepare_window_step(w, spec, recorded_replay=binding.recorded_replay)
            for w in pending[:page_size]
        )
        cycles.append(
            BindingCycle(binding.binding_id, run_binding(store, binding, package, steps, now=now))
        )
    return tuple(cycles)
