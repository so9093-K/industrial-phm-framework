"""XJTU-specific projectors from validated result artifacts into AnalysisView."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from industrial_phm.analysis.view import (
    AnalysisAssetEvidence,
    AnalysisEvidenceIdentity,
    AnalysisObservation,
    AnalysisView,
    AnalysisViewError,
    AnomalyEvidence,
)
from industrial_phm.experiments.result_inspection import (
    ExperimentResultInspectionError,
    inspect_experiment_result,
)
from industrial_phm.experiments.xjtu_lstm_result import (
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
)


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
    source_scope = cast(dict[str, object], document["source_scope"])

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
        identity=_evidence_identity(
            provenance,
            source_scope,
            evaluation_partition="validation",
            evaluation_asset_key="validation_bearings",
        ),
        available_capabilities=tuple(cast(list[str], capability["available"])),
        unsupported_capabilities=tuple(cast(list[str], capability["unsupported_or_not_validated"])),
        inspection=inspection,
        anomaly_evidence=AnomalyEvidence(
            score_semantics_id=cast(str, scoring["score_semantics_id"]),
            score_direction=cast(str, scoring["direction"]),
            feature_names=feature_names,
            assets=tuple(assets),
        ),
    )


def _evidence_identity(
    provenance: dict[str, object],
    source_scope: dict[str, object],
    *,
    evaluation_partition: str,
    evaluation_asset_key: str,
) -> AnalysisEvidenceIdentity:
    return AnalysisEvidenceIdentity(
        dataset_id=cast(str, provenance["dataset_id"]),
        split_id=cast(str, provenance["split_id"]),
        fold_id=cast(str, provenance["fold_id"]),
        code_revision=cast(str, provenance["code_revision"]),
        evaluation_partition=evaluation_partition,
        train_asset_ids=tuple(sorted(cast(list[str], source_scope["train_bearings"]))),
        evaluation_asset_ids=tuple(sorted(cast(list[str], source_scope[evaluation_asset_key]))),
        excluded_scope=tuple(sorted(cast(list[str], source_scope["excluded"]))),
        verified_source_acquisition_count=cast(
            int,
            source_scope["verified_source_acquisition_count"],
        ),
    )
