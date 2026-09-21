"""Presentation read model for user-facing PHM analysis surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from industrial_phm.experiments.result_inspection import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    inspect_experiment_result,
)
from industrial_phm.experiments.xjtu_lstm_result import (
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
)


class AnalysisViewError(ValueError):
    """Raised when validated evidence cannot be represented as an analysis view."""


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
class AnalysisView:
    """Presentation-oriented view over one validated PHM evidence artifact."""

    schema_id: str
    status: str
    evidence_class: str
    artifact_path: str
    score_semantics_id: str
    score_direction: str
    feature_names: tuple[str, ...]
    available_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    assets: tuple[AnalysisAssetEvidence, ...]
    inspection: ExperimentInspection

    def asset(self, asset_id: str) -> AnalysisAssetEvidence:
        """Return one recorded asset evidence scope by identity."""
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        raise AnalysisViewError(f"analysis view does not contain asset_id {asset_id!r}")


def load_xjtu_lstm_analysis_view(path: Path) -> AnalysisView:
    """Project validated XJTU LSTM evidence into a user-facing read model."""
    try:
        inspection = inspect_experiment_result(path)
    except ExperimentResultInspectionError as error:
        raise AnalysisViewError(str(error)) from error

    if inspection.schema_id != XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID:
        raise AnalysisViewError(
            "analysis view currently supports only "
            f"{XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID!r}, got {inspection.schema_id!r}"
        )

    document = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    provenance = cast(dict[str, object], document["provenance"])
    feature_schema = cast(dict[str, object], document["feature_schema"])
    scoring = cast(dict[str, object], document["scoring"])
    evaluation = cast(dict[str, object], document["evaluation"])
    capability = cast(dict[str, object], document["capability_scope"])

    feature_names = tuple(cast(list[str], feature_schema["selected_features"]))
    summaries = {
        cast(str, bearing["asset_id"]): bearing
        for bearing in cast(list[dict[str, object]], evaluation["bearings"])
    }

    assets: list[AnalysisAssetEvidence] = []
    for trajectory in cast(list[dict[str, object]], scoring["trajectories"]):
        asset_id = cast(str, trajectory["asset_id"])
        try:
            summary = summaries[asset_id]
        except KeyError as error:
            raise AnalysisViewError(
                f"validated trajectory {asset_id!r} has no evaluation summary"
            ) from error

        observations = tuple(
            AnalysisObservation(
                source_observation_id=cast(str, observation["source_observation_id"]),
                acquisition_index=cast(int, observation["acquisition_index"]),
                score=float(cast(int | float, observation["score"])),
                feature_residuals=tuple(
                    float(value)
                    for value in cast(list[int | float], observation["feature_residuals"])
                ),
            )
            for observation in cast(list[dict[str, object]], trajectory["observations"])
        )
        assets.append(
            AnalysisAssetEvidence(
                asset_id=asset_id,
                score_window_count=cast(int, summary["score_window_count"]),
                acquisition_order_spearman_rho=float(
                    cast(int | float, summary["acquisition_order_spearman_rho"])
                ),
                late_vs_middle_rank_probability=float(
                    cast(int | float, summary["late_vs_middle_rank_probability"])
                ),
                mean_feature_residuals=tuple(
                    float(value)
                    for value in cast(list[int | float], summary["mean_feature_residuals"])
                ),
                observations=observations,
            )
        )

    return AnalysisView(
        schema_id=inspection.schema_id,
        status=inspection.status,
        evidence_class=cast(str, provenance["evidence_class"]),
        artifact_path=str(path),
        score_semantics_id=cast(str, scoring["score_semantics_id"]),
        score_direction=cast(str, scoring["direction"]),
        feature_names=feature_names,
        available_capabilities=tuple(cast(list[str], capability["available"])),
        unsupported_capabilities=tuple(cast(list[str], capability["unsupported_or_not_validated"])),
        assets=tuple(assets),
        inspection=inspection,
    )
