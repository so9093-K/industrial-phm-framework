import json
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.analysis import (
    AnalysisViewError,
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_XJTU_LSTM_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
_XJTU_HOLDOUT_RESULT = _RESULTS / "xjtu-sy-iforest-fold-1-holdout-v1.json"


def test_xjtu_lstm_analysis_view_preserves_user_facing_evidence() -> None:
    view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)

    assert view.schema_id == "xjtu-lstm-development-result-v1"
    assert view.status == "completed"
    assert view.evidence_class == "retrospective-development-evidence"
    assert view.identity.dataset_id == "xjtu-sy"
    assert view.identity.split_id == "xjtu-sy-condition-stratified-5fold-v1"
    assert view.identity.fold_id == "fold-1"
    assert view.identity.evaluation_partition == "validation"
    assert view.identity.evaluation_asset_ids == (
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    )
    assert view.identity.verified_source_acquisition_count == 9_216
    assert (
        view.require_anomaly_evidence().score_semantics_id == "mean-squared-reconstruction-error-v1"
    )
    assert view.require_anomaly_evidence().score_direction == "higher-is-more-anomalous"
    assert len(view.require_anomaly_evidence().feature_names) == 16
    assert tuple(asset.asset_id for asset in view.require_anomaly_evidence().assets) == (
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    )
    assert (
        sum(asset.score_window_count for asset in view.require_anomaly_evidence().assets) == 2_797
    )
    assert sum(len(asset.observations) for asset in view.require_anomaly_evidence().assets) == 2_797
    assert "anomaly-scoring" in view.available_capabilities
    assert "reconstruction-residual-evidence" in view.available_capabilities
    assert "prognostics-rul" in view.unsupported_capabilities


def test_analysis_view_does_not_recompute_recorded_trajectory() -> None:
    view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)
    document = cast(
        dict[str, object],
        json.loads(_XJTU_LSTM_RESULT.read_text(encoding="utf-8")),
    )
    scoring = cast(dict[str, object], document["scoring"])
    trajectories = cast(list[dict[str, object]], scoring["trajectories"])
    first_recorded = cast(list[dict[str, object]], trajectories[0]["observations"])[0]

    first_view = view.require_anomaly_evidence().assets[0].observations[0]
    assert first_view.source_observation_id == first_recorded["source_observation_id"]
    assert first_view.acquisition_index == first_recorded["acquisition_index"]
    assert first_view.score == first_recorded["score"]
    assert first_view.feature_residuals == tuple(
        cast(list[float], first_recorded["feature_residuals"])
    )


def test_analysis_view_keeps_pipeline_transparency_for_drill_down() -> None:
    view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)

    assert view.inspection.schema_id == view.schema_id
    assert tuple(stage.name for stage in view.inspection.stages) == (
        "Source",
        "Canonical",
        "Feature",
        "Preprocessing",
        "Reference",
        "Sequence Construction",
        "Population",
        "Model",
        "Scoring",
        "Evaluation",
        "Capability",
        "Provenance",
    )


def test_analysis_view_asset_lookup_uses_recorded_identity() -> None:
    view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)

    assert view.require_anomaly_evidence().asset("Bearing2_2").asset_id == "Bearing2_2"
    with pytest.raises(AnalysisViewError, match="does not contain asset_id"):
        view.require_anomaly_evidence().asset("Bearing9_9")


def test_analysis_view_rejects_unsupported_experiment_schema() -> None:
    with pytest.raises(AnalysisViewError, match="currently supports only"):
        load_xjtu_lstm_analysis_view(_XJTU_HOLDOUT_RESULT)


_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"


def test_capabilities_compose_instead_of_collapsing_into_one_record() -> None:
    """An artifact without a capability must leave it absent, not empty-filled."""
    anomaly_view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)
    prognostics_view = load_xjtu_rul_analysis_view(_RUL_RESULT)

    assert anomaly_view.anomaly_evidence is not None
    assert anomaly_view.prognostics_evidence is None
    assert prognostics_view.prognostics_evidence is not None
    assert prognostics_view.anomaly_evidence is None


def test_missing_capability_fails_explicitly() -> None:
    prognostics_view = load_xjtu_rul_analysis_view(_RUL_RESULT)
    anomaly_view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)

    with pytest.raises(AnalysisViewError, match="carries no anomaly evidence"):
        prognostics_view.require_anomaly_evidence()
    with pytest.raises(AnalysisViewError, match="carries no prognostics evidence"):
        anomaly_view.require_prognostics_evidence()


def test_prognostics_view_preserves_recorded_target_semantics() -> None:
    evidence = load_xjtu_rul_analysis_view(_RUL_RESULT).require_prognostics_evidence()

    assert evidence.target_unit == "acquisition-interval"
    assert evidence.endpoint_semantics == "last-recorded-acquisition"
    assert evidence.target_formula == "N-k"
    assert evidence.target_is_clipped is False
    assert evidence.target_is_normalized is False
    assert evidence.support_first_acquisition == 8
    assert evidence.support_prediction_count == 2_797


def test_prognostics_view_declares_no_selected_primary_method() -> None:
    """No method selection is validated, so a surface must not present one as the answer."""
    evidence = load_xjtu_rul_analysis_view(_RUL_RESULT).require_prognostics_evidence()

    assert evidence.primary_method_id is None
    assert len(evidence.methods) == 3


def test_prognostics_view_keeps_per_asset_evidence_for_every_method() -> None:
    evidence = load_xjtu_rul_analysis_view(_RUL_RESULT).require_prognostics_evidence()

    for method in evidence.methods:
        assert {asset.asset_id for asset in method.assets} == {
            "Bearing1_2",
            "Bearing2_2",
            "Bearing3_2",
        }
        assert all(asset.prediction_count > 0 for asset in method.assets)


def test_prognostics_view_rejects_an_anomaly_artifact() -> None:
    with pytest.raises(AnalysisViewError, match="expected"):
        load_xjtu_rul_analysis_view(_XJTU_LSTM_RESULT)
