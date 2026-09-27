from pathlib import Path

from industrial_phm.analysis import (
    load_xjtu_rul_analysis_view,
    prognostics_asset_ids,
    summarize_prognostics_for_asset,
)

_RESULTS = Path(__file__).parents[2] / "docs" / "research" / "results"
_DEFAULT_OPERATIONS_RUL = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"


def test_default_operations_development_rul_artifact_is_readable_and_non_operational() -> None:
    view = load_xjtu_rul_analysis_view(_DEFAULT_OPERATIONS_RUL)

    asset_ids = prognostics_asset_ids(view)
    summary = summarize_prognostics_for_asset(view, asset_ids[0])

    assert asset_ids == ("Bearing1_2", "Bearing2_2", "Bearing3_2")
    assert summary.primary_method_id is None
    assert summary.uncertainty_interval_available is False
    assert summary.physical_failure_threshold_validated is False
    assert len(summary.methods) == 3
    assert summary.target_unit == "acquisition-interval"
    assert summary.endpoint_semantics == "last-recorded-acquisition"
    assert summary.evidence_class
