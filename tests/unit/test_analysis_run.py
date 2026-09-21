from pathlib import Path

import pytest

from industrial_phm.analysis import (
    AnalysisRunError,
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
    assert result.analysis.asset("Bearing1_2").observations


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
