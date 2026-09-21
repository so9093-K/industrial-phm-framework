import json
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.analysis import AnalysisViewError, load_xjtu_lstm_analysis_view

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_XJTU_LSTM_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
_XJTU_HOLDOUT_RESULT = _RESULTS / "xjtu-sy-iforest-fold-1-holdout-v1.json"


def test_xjtu_lstm_analysis_view_preserves_user_facing_evidence() -> None:
    view = load_xjtu_lstm_analysis_view(_XJTU_LSTM_RESULT)

    assert view.schema_id == "xjtu-lstm-development-result-v1"
    assert view.status == "completed"
    assert view.evidence_class == "retrospective-development-evidence"
    assert view.score_semantics_id == "mean-squared-reconstruction-error-v1"
    assert view.score_direction == "higher-is-more-anomalous"
    assert len(view.feature_names) == 16
    assert tuple(asset.asset_id for asset in view.assets) == (
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    )
    assert sum(asset.score_window_count for asset in view.assets) == 2_797
    assert sum(len(asset.observations) for asset in view.assets) == 2_797
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

    first_view = view.assets[0].observations[0]
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

    assert view.asset("Bearing2_2").asset_id == "Bearing2_2"
    with pytest.raises(AnalysisViewError, match="does not contain asset_id"):
        view.asset("Bearing9_9")


def test_analysis_view_rejects_unsupported_experiment_schema() -> None:
    with pytest.raises(AnalysisViewError, match="currently supports only"):
        load_xjtu_lstm_analysis_view(_XJTU_HOLDOUT_RESULT)
