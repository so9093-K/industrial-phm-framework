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
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
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


def load_xjtu_rul_analysis_view(path: Path) -> AnalysisView:
    """Project validated XJTU three-model RUL evidence into a user-facing read model."""
    inspection = _inspect(path)
    if inspection.schema_id != XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID:
        raise AnalysisViewError(
            f"expected {XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID!r}, "
            f"got {inspection.schema_id!r}"
        )

    document = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    provenance = cast(dict[str, object], document["provenance"])
    target = cast(dict[str, object], document["target"])
    capability = cast(dict[str, object], document["capability_scope"])
    comparison = cast(dict[str, object], document["common_support_comparison"])
    support = cast(dict[str, object], comparison["support"])
    evaluations = cast(dict[str, object], comparison["evaluations"])
    kinds = {
        cast(str, method["method_id"]): cast(str, method["kind"])
        for method in cast(list[dict[str, object]], document["methods"])
    }
    last_predictions = {
        cast(str, method["method_id"]): _last_recorded_predictions(method)
        for method in cast(list[dict[str, object]], document["methods"])
    }

    methods: list[PrognosticsMethodEvidence] = []
    for method_id in sorted(evaluations):
        evaluation = cast(dict[str, object], evaluations[method_id])
        try:
            kind = kinds[method_id]
        except KeyError as error:
            raise AnalysisViewError(
                f"evaluated method {method_id!r} has no method declaration"
            ) from error
        methods.append(
            PrognosticsMethodEvidence(
                method_id=method_id,
                kind=kind,
                mean_absolute_error=_number(evaluation, "mean_asset_mean_absolute_error"),
                root_mean_squared_error=_number(evaluation, "mean_asset_root_mean_squared_error"),
                mean_signed_error=_number(evaluation, "mean_asset_mean_signed_error"),
                normalized_mean_absolute_error=_number(
                    evaluation, "mean_asset_normalized_mean_absolute_error"
                ),
                assets=tuple(
                    _prognostics_asset(bearing, last_predictions[method_id])
                    for bearing in cast(list[dict[str, object]], evaluation["bearings"])
                ),
            )
        )

    return AnalysisView(
        schema_id=inspection.schema_id,
        status=inspection.status,
        evidence_class=cast(str, provenance["evidence_class"]),
        artifact_path=str(path),
        available_capabilities=tuple(cast(list[str], capability["available"])),
        unsupported_capabilities=tuple(cast(list[str], capability["unsupported_or_not_validated"])),
        inspection=inspection,
        prognostics_evidence=PrognosticsEvidence(
            target_definition_id=cast(str, target["definition_id"]),
            target_unit=cast(str, target["unit"]),
            target_formula=cast(str, target["formula"]),
            endpoint_semantics=cast(str, target["endpoint_semantics"]),
            prediction_alignment=cast(str, target["prediction_alignment"]),
            support_definition=cast(str, support["definition"]),
            support_first_acquisition=cast(int, support["first_acquisition"]),
            support_prediction_count=cast(int, support["total_prediction_count"]),
            methods=tuple(methods),
        ),
    )


def _inspect(path: Path) -> ExperimentInspection:
    try:
        return inspect_experiment_result(path)
    except ExperimentResultInspectionError as error:
        raise AnalysisViewError(str(error)) from error


def _number(values: dict[str, object], key: str) -> float:
    return float(cast(int | float, values[key]))


def _last_recorded_predictions(method: dict[str, object]) -> dict[str, tuple[int, float]]:
    recorded: dict[str, tuple[int, float]] = {}
    for trajectory in cast(list[dict[str, object]], method["predictions"]):
        observations = cast(list[dict[str, object]], trajectory["observations"])
        if not observations:
            continue
        final = max(observations, key=lambda item: cast(int, item["acquisition_index"]))
        recorded[cast(str, trajectory["asset_id"])] = (
            cast(int, final["acquisition_index"]),
            float(cast(int | float, final["predicted_remaining_useful_life"])),
        )
    return recorded


def _prognostics_asset(
    bearing: dict[str, object],
    last_predictions: dict[str, tuple[int, float]],
) -> PrognosticsAssetEvidence:
    asset_id = cast(str, bearing["asset_id"])
    try:
        acquisition_index, remaining_useful_life = last_predictions[asset_id]
    except KeyError as error:
        raise AnalysisViewError(
            f"evaluated asset {asset_id!r} has no recorded prediction trajectory"
        ) from error
    return PrognosticsAssetEvidence(
        asset_id=asset_id,
        prediction_count=cast(int, bearing["prediction_count"]),
        mean_absolute_error=_number(bearing, "mean_absolute_error"),
        root_mean_squared_error=_number(bearing, "root_mean_squared_error"),
        mean_signed_error=_number(bearing, "mean_signed_error"),
        normalized_mean_absolute_error=_number(bearing, "normalized_mean_absolute_error"),
        last_recorded_acquisition_index=acquisition_index,
        last_recorded_remaining_useful_life=remaining_useful_life,
    )
