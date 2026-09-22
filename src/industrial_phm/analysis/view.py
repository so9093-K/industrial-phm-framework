"""Presentation read model for user-facing PHM analysis surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from industrial_phm.experiments.result_inspection import ExperimentInspection


class AnalysisViewError(ValueError):
    """Raised when validated evidence cannot be represented as an analysis view."""


@dataclass(frozen=True, slots=True)
class AnalysisEvidenceIdentity:
    """Artifact-owned identity used to decide whether evidence can share one surface."""

    dataset_id: str
    split_id: str
    fold_id: str
    code_revision: str
    evaluation_partition: str
    train_asset_ids: tuple[str, ...]
    evaluation_asset_ids: tuple[str, ...]
    excluded_scope: tuple[str, ...]
    verified_source_acquisition_count: int


@dataclass(frozen=True, slots=True)
class AnalysisObservation:
    """One recorded score observation with model evidence."""

    source_observation_id: str
    acquisition_index: int
    score: float
    feature_residuals: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class AnalysisAssetEvidence:
    """Recorded trajectory and aggregate evidence for one asset scope."""

    asset_id: str
    score_window_count: int
    acquisition_order_spearman_rho: float
    late_vs_middle_rank_probability: float
    mean_feature_residuals: tuple[float, ...]
    observations: tuple[AnalysisObservation, ...]


@dataclass(frozen=True, slots=True)
class AnomalyEvidence:
    """Validated anomaly-scoring evidence for one artifact."""

    score_semantics_id: str
    score_direction: str
    feature_names: tuple[str, ...]
    assets: tuple[AnalysisAssetEvidence, ...]

    def asset(self, asset_id: str) -> AnalysisAssetEvidence:
        """Return one recorded asset evidence scope by identity."""
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        raise AnalysisViewError(f"anomaly evidence does not contain asset_id {asset_id!r}")


@dataclass(frozen=True, slots=True)
class PrognosticsAssetEvidence:
    """Point-error evidence for one asset under one prediction method.

    ``last_recorded_*`` fields repeat the final recorded prediction of the validation run.
    They are read back from the artifact, never recomputed, and describe a retrospective
    run rather than a live estimate.
    """

    asset_id: str
    prediction_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_signed_error: float
    normalized_mean_absolute_error: float
    last_recorded_acquisition_index: int
    last_recorded_remaining_useful_life: float


@dataclass(frozen=True, slots=True)
class PrognosticsMethodEvidence:
    """Aggregate and per-asset evidence for one RUL prediction method."""

    method_id: str
    kind: str
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_signed_error: float
    normalized_mean_absolute_error: float
    assets: tuple[PrognosticsAssetEvidence, ...]


@dataclass(frozen=True, slots=True)
class PrognosticsEvidence:
    """Validated RUL point-estimate evidence for one artifact.

    ``primary_method_id`` stays ``None`` while no method selection is validated. A surface
    that shows several methods must present them as comparison evidence, not as several
    competing answers for the same asset.
    """

    target_definition_id: str
    target_unit: str
    target_formula: str
    endpoint_semantics: str
    prediction_alignment: str
    target_is_clipped: bool
    target_is_normalized: bool
    support_definition: str
    support_first_acquisition: int
    support_prediction_count: int
    methods: tuple[PrognosticsMethodEvidence, ...]
    primary_method_id: str | None = None

    def method(self, method_id: str) -> PrognosticsMethodEvidence:
        """Return one compared method by identity."""
        for method in self.methods:
            if method.method_id == method_id:
                return method
        raise AnalysisViewError(f"prognostics evidence does not contain method {method_id!r}")


@dataclass(frozen=True, slots=True)
class AnalysisView:
    """Presentation-oriented view over one validated PHM evidence artifact.

    Capabilities compose instead of collapsing into one nullable record: an artifact that
    carries no prognostics evidence leaves ``prognostics_evidence`` absent rather than
    filling RUL fields with empty values.
    """

    schema_id: str
    status: str
    evidence_class: str
    artifact_path: str
    identity: AnalysisEvidenceIdentity
    available_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    inspection: ExperimentInspection
    anomaly_evidence: AnomalyEvidence | None = None
    prognostics_evidence: PrognosticsEvidence | None = None

    def require_anomaly_evidence(self) -> AnomalyEvidence:
        """Return anomaly evidence or fail explicitly when the artifact carries none."""
        if self.anomaly_evidence is None:
            raise AnalysisViewError(f"{self.schema_id!r} carries no anomaly evidence")
        return self.anomaly_evidence

    def require_prognostics_evidence(self) -> PrognosticsEvidence:
        """Return prognostics evidence or fail explicitly when the artifact carries none."""
        if self.prognostics_evidence is None:
            raise AnalysisViewError(f"{self.schema_id!r} carries no prognostics evidence")
        return self.prognostics_evidence


