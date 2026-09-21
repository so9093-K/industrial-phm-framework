from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.analysis import (
    AnalysisViewError,
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
    prognostics_asset_ids,
    summarize_prognostics_for_asset,
)

_RESULTS = Path(__file__).parents[2] / "docs" / "research" / "results"
_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"
_LSTM_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"


def _summary(asset_id: str = "Bearing1_2"):
    return summarize_prognostics_for_asset(load_xjtu_rul_analysis_view(_RUL_RESULT), asset_id)


def test_summary_states_what_one_predicted_unit_means() -> None:
    """A surface must never show a bare number without its target semantics."""
    summary = _summary()

    assert summary.target_unit == "acquisition-interval"
    assert summary.endpoint_semantics == "last-recorded-acquisition"
    assert "acquisition-interval until the last recorded acquisition" in summary.target_description
    assert summary.target_formula == "N-k"


def test_summary_marks_uncertainty_and_failure_threshold_as_unavailable() -> None:
    summary = _summary()

    assert summary.uncertainty_interval_available is False
    assert summary.physical_failure_threshold_validated is False


def test_summary_capabilities_fail_closed_when_scope_omits_them() -> None:
    view = load_xjtu_rul_analysis_view(_RUL_RESULT)
    view = replace(
        view,
        available_capabilities=("prognostics-rul-point-estimate",),
        unsupported_capabilities=(),
    )

    summary = summarize_prognostics_for_asset(view, "Bearing1_2")

    assert summary.uncertainty_interval_available is False
    assert summary.physical_failure_threshold_validated is False


def test_summary_declares_no_operational_method_selection() -> None:
    summary = _summary()

    assert summary.primary_method_id is None
    assert len(summary.methods) == 3


def test_summary_keeps_recorded_estimates_without_clipping() -> None:
    """Ridge records a negative estimate; a surface must not floor it at zero."""
    summary = _summary()

    ridge = next(row for row in summary.methods if "ridge" in row.method_id)
    assert ridge.last_recorded_remaining_useful_life < 0.0
    assert summary.has_negative_estimate is True
    assert summary.target_is_clipped is False
    low, high = summary.estimate_range
    assert low < 0.0 < high


def test_summary_reports_the_as_of_acquisition_from_recorded_predictions() -> None:
    summary = _summary()

    assert {row.last_recorded_acquisition_index for row in summary.methods} == {161}
    assert all(row.prediction_count > 0 for row in summary.methods)


def test_summary_requires_every_method_to_cover_the_asset() -> None:
    with pytest.raises(AnalysisViewError, match="no recorded evidence for asset"):
        _summary("Bearing9_9")


def test_prognostics_asset_ids_are_shared_across_methods() -> None:
    assert prognostics_asset_ids(load_xjtu_rul_analysis_view(_RUL_RESULT)) == (
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    )


def test_summary_refuses_an_artifact_without_prognostics_evidence() -> None:
    view = load_xjtu_lstm_analysis_view(_LSTM_RESULT)

    with pytest.raises(AnalysisViewError, match="carries no prognostics evidence"):
        summarize_prognostics_for_asset(view, "Bearing1_2")
