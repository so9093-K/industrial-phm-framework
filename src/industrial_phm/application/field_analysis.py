"""Operational field-analysis producer for prepared registered FILE snapshots."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from industrial_phm.adapters import CsvSensorAdapter
from industrial_phm.application.file_source_registration import (
    load_registered_file_source_observation,
)
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    FileSourceMode,
    RegisteredSource,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    extract_vibration_features,
)

FIELD_VIBRATION_FEATURE_CAPABILITY_ID = "field-vibration-statistical-features-v1"


@dataclass(frozen=True, slots=True)
class OperationalVibrationFeatureEvidence:
    """Feature evidence produced from one exact operational source snapshot.

    This evidence describes measured waveform statistics only. It is not an anomaly,
    health state, diagnosis, finding, alert, or maintenance recommendation.
    """

    evidence_id: str
    analysis_run_id: str
    capability_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    values: Sequence[float]
    source_snapshot_sha256: str

    def __post_init__(self) -> None:
        feature_names = tuple(self.feature_names)
        values = tuple(float(value) for value in self.values)

        for value, field_name in (
            (self.evidence_id, "evidence_id"),
            (self.analysis_run_id, "analysis_run_id"),
            (self.capability_id, "capability_id"),
            (self.feature_set_id, "feature_set_id"),
            (self.source_snapshot_sha256, "source_snapshot_sha256"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
            if value != value.strip():
                raise ValueError(f"{field_name} must not contain surrounding whitespace")

        if not feature_names:
            raise ValueError("feature_names must contain at least one feature")
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("feature_names must contain unique values")
        if len(feature_names) != len(values):
            raise ValueError("feature_names and values must have the same length")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("feature values must be finite")

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class RegisteredFieldFeatureAnalysis:
    """One operational AnalysisRun plus its capability-specific feature evidence."""

    run: AnalysisRun
    evidence: OperationalVibrationFeatureEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.run, AnalysisRun):
            raise ValueError("run must be an AnalysisRun")
        if not isinstance(self.evidence, OperationalVibrationFeatureEvidence):
            raise ValueError("evidence must be OperationalVibrationFeatureEvidence")
        if self.evidence.analysis_run_id != self.run.analysis_run_id:
            raise ValueError("feature evidence analysis_run_id must match the run")
        if self.evidence.capability_id not in self.run.capability_ids:
            raise ValueError("feature evidence capability_id must be declared by the run")


def run_registered_file_feature_analysis(
    source: RegisteredSource,
    *,
    clock: Callable[[], datetime] | None = None,
) -> RegisteredFieldFeatureAnalysis:
    """Validate and analyze one registered FILE snapshot using the fixed vibration feature set.

    History directories are intentionally excluded from this first operational producer.
    The existing AnalysisRun contract requires absolute observation time, so snapshots
    without timezone-aware source timestamps also fail closed rather than inventing time.
    """
    if not isinstance(source, RegisteredSource):
        raise ValueError("source must be RegisteredSource")
    config = source.config
    if not isinstance(config, FileSourceConfig):
        raise ValueError("operational field feature analysis currently supports FILE sources only")
    if config.mode != FileSourceMode.SNAPSHOT:
        raise ValueError(
            "operational field feature analysis currently supports FILE snapshot mode only"
        )
    if config.timestamp_column is None:
        raise ValueError("operational field feature analysis requires an explicit timestamp column")

    now = clock or (lambda: datetime.now(UTC))
    started_at = _require_aware_time(now(), "analysis started_at")

    loaded = load_registered_file_source_observation(source)
    observation = loaded.latest
    if observation.observed_start_at is None or observation.observed_end_at is None:
        raise ValueError("operational analysis requires explicit observed start/end timestamps")
    if observation.observed_start_at.utcoffset() is None:
        raise ValueError(
            "operational analysis requires timezone-aware source timestamps; "
            "naive CSV timestamps need an explicit source-time mapping before analysis"
        )

    adapter = CsvSensorAdapter(config.to_csv_sensor_layout())
    series_values = tuple(adapter.iter_series(Path(config.source_path)))
    if len(series_values) != 1:
        raise AssertionError("FILE snapshot adapter unexpectedly produced multiple series")
    feature_vector = extract_vibration_features(series_values[0])

    completed_at = _require_aware_time(now(), "analysis completed_at")
    if completed_at < started_at:
        raise ValueError("analysis completed_at must not be before started_at")

    analysis_run_id = f"analysis-run-{uuid4()}"
    evidence_id = f"evidence-{uuid4()}"
    source_snapshots = () if observation.source_snapshot is None else (observation.source_snapshot,)
    run = AnalysisRun(
        analysis_run_id=analysis_run_id,
        asset_id=observation.asset_id,
        source_id=observation.source_id,
        measurement_point_id=observation.measurement_point_id,
        observed_start_at=observation.observed_start_at,
        observed_end_at=observation.observed_end_at,
        started_at=started_at,
        completed_at=completed_at,
        data_quality=observation.data_quality,
        source_snapshots=source_snapshots,
        capability_ids=(FIELD_VIBRATION_FEATURE_CAPABILITY_ID,),
    )
    evidence = OperationalVibrationFeatureEvidence(
        evidence_id=evidence_id,
        analysis_run_id=analysis_run_id,
        capability_id=FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        feature_names=feature_vector.feature_names,
        values=feature_vector.values,
        source_snapshot_sha256=(
            observation.source_snapshot.sha256
            if observation.source_snapshot is not None
            else str(feature_vector.metadata["source_sha256"])
        ),
    )
    return RegisteredFieldFeatureAnalysis(run=run, evidence=evidence)


def _require_aware_time(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value
