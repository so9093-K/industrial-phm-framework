"""Drive PHM bindings from their step sources (ADR-0025).

The runner turns each new acquisition snapshot into a step projected onto the bound package's
input schema, then commits it through :class:`SqlitePhmAnalysisStore`. A package that cannot be
loaded marks only its binding unavailable; other bindings keep running.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
    read_snapshot_waveform,
)
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
    load_model_package,
)

_SnapshotFeatures = Callable[[CanonicalTimeSeries], Mapping[str, float]]


def _vibration_statistical(series: CanonicalTimeSeries) -> Mapping[str, float]:
    vector = extract_vibration_features(series)
    return dict(zip(vector.feature_names, vector.values, strict=True))


SNAPSHOT_FEATURE_SETS: Mapping[str, _SnapshotFeatures] = {
    VIBRATION_STATISTICAL_FEATURE_SET_ID: _vibration_statistical,
}


def prepare_snapshot_step(snapshot: AcquisitionSnapshot, spec: PackageInputSpec) -> PreparedStep:
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
    features, reason = _snapshot_features(snapshot, spec)
    return PreparedStep(
        step_key=snapshot.step_key,
        position=snapshot.ordinal,
        replay=snapshot.replay,
        input_reference=reference,
        event_start=snapshot.event_at,
        features=features,
        context=context,
        skip_reason=reason,
    )


def _snapshot_features(
    snapshot: AcquisitionSnapshot, spec: PackageInputSpec
) -> tuple[tuple[float, ...] | None, str | None]:
    reason = _snapshot_incompatibility(snapshot, spec)
    if reason is not None:
        return None, reason
    extractor = SNAPSHOT_FEATURE_SETS.get(spec.feature_set_id)
    if extractor is None:
        return None, f"unsupported feature set for snapshots: {spec.feature_set_id}"
    try:
        features = extractor(read_snapshot_waveform(snapshot))
    except (AcquisitionSnapshotError, VibrationFeatureError, ValueError) as error:
        return None, f"snapshot unreadable: {error}"
    missing = [name for name in spec.feature_names if name not in features]
    if missing:
        return None, f"features missing from step: {missing[:3]}"
    return tuple(features[name] for name in spec.feature_names), None


def _snapshot_incompatibility(snapshot: AcquisitionSnapshot, spec: PackageInputSpec) -> str | None:
    if spec.step_kind is not StepKind.ACQUISITION_SNAPSHOT:
        return f"package expects {spec.step_kind.value} steps"
    if tuple(snapshot.channels) != tuple(spec.channels):
        return f"channels differ from the package input: {list(snapshot.channels)}"
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
    for binding in store.list_bindings():
        if binding.step_kind is not StepKind.ACQUISITION_SNAPSHOT:
            continue
        cycles.append(_run_one(store, snapshots, packages, binding, page_size, now))
    return tuple(cycles)


def _run_one(
    store: SqlitePhmAnalysisStore,
    snapshots: SqliteAcquisitionSnapshotRepository,
    packages: PackageCache,
    binding: PhmBinding,
    page_size: int,
    now: Callable[[], datetime],
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
    steps = (prepare_snapshot_step(snapshot, spec) for snapshot in pending)
    return BindingCycle(binding.binding_id, run_binding(store, binding, package, steps, now=now))
