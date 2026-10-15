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
class AnalysisView:
    """Presentation-oriented view over one validated PHM evidence artifact."""

    schema_id: str
    status: str
    evidence_class: str
    artifact_path: str
    identity: AnalysisEvidenceIdentity
    available_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    inspection: ExperimentInspection
    anomaly_evidence: AnomalyEvidence | None = None

    def require_anomaly_evidence(self) -> AnomalyEvidence:
        """Return anomaly evidence or fail explicitly when the artifact carries none."""
        if self.anomaly_evidence is None:
            raise AnalysisViewError(f"{self.schema_id!r} carries no anomaly evidence")
        return self.anomaly_evidence
