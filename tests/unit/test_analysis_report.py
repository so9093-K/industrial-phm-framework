from pathlib import Path

import pytest

from industrial_phm.analysis import (
    AnalysisReportError,
    load_xjtu_lstm_analysis_view,
    render_analysis_report_markdown,
    write_analysis_report_markdown,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_ANOMALY_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"


def test_report_is_deterministic_for_same_read_models() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)

    first = render_analysis_report_markdown(anomaly, "Bearing1_2")
    second = render_analysis_report_markdown(anomaly, "Bearing1_2")

    assert first == second
    assert "# PHM 분석 보고서" in first
    assert "## 이상 변화 요약" in first


def test_report_preserves_inspection_warnings() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)

    rendered = render_analysis_report_markdown(anomaly, "Bearing1_2")

    assert "### 이상 분석 기술 경고" in rendered
    assert "not a fresh holdout or test result" in rendered


def test_report_writer_matches_renderer_bytes(tmp_path: Path) -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)
    output = tmp_path / "report.md"

    write_analysis_report_markdown(anomaly, "Bearing2_2", output)

    assert output.read_text(encoding="utf-8") == render_analysis_report_markdown(
        anomaly, "Bearing2_2"
    )


def test_report_rejects_unknown_asset() -> None:
    anomaly = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)

    with pytest.raises(AnalysisReportError, match="Bearing9_9"):
        render_analysis_report_markdown(anomaly, "Bearing9_9")
