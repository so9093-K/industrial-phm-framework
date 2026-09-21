from pathlib import Path

import pytest

from industrial_phm.analysis import (
    AnalysisReportError,
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
    render_analysis_report_markdown,
    write_analysis_report_markdown,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_ANOMALY_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"


def test_report_is_deterministic_for_same_read_models() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)

    first = render_analysis_report_markdown(
        anomaly,
        "Bearing1_2",
        prognostics=prognostics,
    )
    second = render_analysis_report_markdown(
        anomaly,
        "Bearing1_2",
        prognostics=prognostics,
    )

    assert first == second
    assert "# PHM Analysis Report" in first
    assert "## Anomaly evidence" in first
    assert "## Attached prognostics evidence" in first


def test_report_keeps_attached_prognostics_as_separate_evidence() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)

    rendered = render_analysis_report_markdown(
        anomaly,
        "Bearing1_2",
        prognostics=prognostics,
    )

    assert "compatible-separate-revision" in rendered
    assert "separate retrospective evidence" in rendered
    assert "Exact source byte identity is not recorded" in rendered
    assert "No operational primary method is asserted" in rendered
    assert "Uncertainty interval available: false" in rendered
    assert "Physical failure threshold validated: false" in rendered


def test_report_preserves_inspection_warnings() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)

    rendered = render_analysis_report_markdown(
        anomaly,
        "Bearing1_2",
        prognostics=prognostics,
    )

    assert "recorded-end acquisition interval" in rendered
    assert "holdout test is excluded" in rendered
    assert "Point-error metrics do not create uncertainty intervals" in rendered


def test_report_writer_matches_renderer_bytes(tmp_path: Path) -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    prognostics = load_xjtu_rul_analysis_view(_RUL_RESULT)
    output = tmp_path / "report.md"

    write_analysis_report_markdown(
        anomaly,
        "Bearing2_2",
        output,
        prognostics=prognostics,
    )

    assert output.read_text(encoding="utf-8") == render_analysis_report_markdown(
        anomaly,
        "Bearing2_2",
        prognostics=prognostics,
    )


def test_report_rejects_unknown_asset() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)

    with pytest.raises(AnalysisReportError, match="Bearing9_9"):
        render_analysis_report_markdown(anomaly, "Bearing9_9")
