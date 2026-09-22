from pathlib import Path

import pytest

from industrial_phm.adapters import XjtuSyValidationReport
from industrial_phm.analysis import (
    AnalysisRunError,
    plan_xjtu_lstm_analysis,
    run_xjtu_lstm_analysis_from_source,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULT = (
    _REPOSITORY_ROOT
    / "docs"
    / "research"
    / "results"
    / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
)


def test_analysis_run_connects_existing_runner_to_validated_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "prepared-xjtu"
    output = tmp_path / "analysis.json"
    captured: dict[str, object] = {}

    def fake_runner(
        observed_source: Path,
        observed_output: Path,
        *,
        code_revision: str,
    ) -> None:
        captured["source"] = observed_source
        captured["output"] = observed_output
        captured["code_revision"] = code_revision
        observed_output.write_bytes(_RESULT.read_bytes())

    monkeypatch.setattr(
        "industrial_phm.analysis.run.run_xjtu_lstm_development_evaluation",
        fake_runner,
    )

    result = run_xjtu_lstm_analysis_from_source(
        source,
        output,
        code_revision="a" * 40,
    )

    assert captured == {
        "source": source,
        "output": output,
        "code_revision": "a" * 40,
    }
    assert result.source == source
    assert result.result_path == output
    assert result.analysis.schema_id == "xjtu-lstm-development-result-v1"
    assert result.analysis.require_anomaly_evidence().asset("Bearing1_2").observations


def test_analysis_run_exposes_execution_failure_as_application_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(
        source: Path,
        output: Path,
        *,
        code_revision: str,
    ) -> None:
        del source, output, code_revision
        raise ValueError("source profile drift")

    monkeypatch.setattr(
        "industrial_phm.analysis.run.run_xjtu_lstm_development_evaluation",
        fake_runner,
    )

    with pytest.raises(AnalysisRunError, match=r"analysis execution failed.*source profile drift"):
        run_xjtu_lstm_analysis_from_source(
            tmp_path / "source",
            tmp_path / "result.json",
            code_revision="b" * 40,
        )


def test_analysis_run_resolves_current_revision_when_not_supplied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "prepared-xjtu"
    output = tmp_path / "analysis.json"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "industrial_phm.analysis.run._resolve_current_git_revision",
        lambda: "c" * 40,
    )

    def fake_runner(
        observed_source: Path,
        observed_output: Path,
        *,
        code_revision: str,
    ) -> None:
        captured["source"] = observed_source
        captured["output"] = observed_output
        captured["code_revision"] = code_revision
        observed_output.write_bytes(_RESULT.read_bytes())

    monkeypatch.setattr(
        "industrial_phm.analysis.run.run_xjtu_lstm_development_evaluation",
        fake_runner,
    )

    result = run_xjtu_lstm_analysis_from_source(source, output)

    assert captured == {
        "source": source,
        "output": output,
        "code_revision": "c" * 40,
    }
    assert result.analysis.schema_id == "xjtu-lstm-development-result-v1"


def test_analysis_run_plan_reports_validated_source_without_executing_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "prepared-xjtu"
    output = tmp_path / "analysis.json"

    monkeypatch.setattr(
        "industrial_phm.analysis.run.validate_xjtu_source",
        lambda observed_source: XjtuSyValidationReport(
            source=observed_source,
            full=False,
            operating_condition_count=3,
            bearing_run_count=15,
            acquisition_count=10_000,
            checked_acquisition_count=30,
            channels=("Horizontal_vibration_signals", "Vertical_vibration_signals"),
            samples_per_acquisition=32_768,
            sampling_rate_hz=25_600.0,
            profile_issues=(),
        ),
    )

    plan = plan_xjtu_lstm_analysis(source, output)

    assert plan.ready_to_run is True
    assert plan.source == source
    assert plan.result_path == output
    assert plan.source_acquisition_count == 10_000
    assert plan.bearing_run_count == 15
    assert plan.checked_acquisition_count == 30
    assert "fit deterministic CPU LSTM autoencoder" in plan.pipeline_stages
    assert plan.blockers == ()
    assert any("clean tracked Git checkout" in warning for warning in plan.warnings)


def test_analysis_run_plan_exposes_source_profile_mismatch_as_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "prepared-xjtu"

    monkeypatch.setattr(
        "industrial_phm.analysis.run.validate_xjtu_source",
        lambda observed_source: XjtuSyValidationReport(
            source=observed_source,
            full=False,
            operating_condition_count=3,
            bearing_run_count=14,
            acquisition_count=9_900,
            checked_acquisition_count=28,
            channels=("Horizontal_vibration_signals", "Vertical_vibration_signals"),
            samples_per_acquisition=32_768,
            sampling_rate_hz=25_600.0,
            profile_issues=("missing Bearing3_5",),
        ),
    )

    plan = plan_xjtu_lstm_analysis(source, tmp_path / "analysis.json")

    assert plan.ready_to_run is False
    assert plan.blockers == ("source profile mismatch: missing Bearing3_5",)


def test_analysis_run_plan_reports_missing_source_without_raising(tmp_path: Path) -> None:
    plan = plan_xjtu_lstm_analysis(
        tmp_path / "missing-source",
        tmp_path / "analysis.json",
    )

    assert plan.ready_to_run is False
    assert plan.source_acquisition_count is None
    assert plan.bearing_run_count is None
    assert any("does not exist" in blocker for blocker in plan.blockers)


def test_analysis_run_plan_warns_before_replacing_existing_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "prepared-xjtu"
    output = tmp_path / "analysis.json"
    output.write_text("existing", encoding="utf-8")

    monkeypatch.setattr(
        "industrial_phm.analysis.run.validate_xjtu_source",
        lambda observed_source: XjtuSyValidationReport(
            source=observed_source,
            full=False,
            operating_condition_count=3,
            bearing_run_count=15,
            acquisition_count=10_000,
            checked_acquisition_count=30,
            channels=("Horizontal_vibration_signals", "Vertical_vibration_signals"),
            samples_per_acquisition=32_768,
            sampling_rate_hz=25_600.0,
            profile_issues=(),
        ),
    )

    plan = plan_xjtu_lstm_analysis(source, output)

    assert plan.ready_to_run is True
    assert any("will be replaced" in warning for warning in plan.warnings)
