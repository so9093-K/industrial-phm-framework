from pathlib import Path

import pytest

import industrial_phm.cli as cli


def test_analysis_report_cli_writes_deterministic_markdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = Path(__file__).parents[2]
    results = repository_root / "docs" / "research" / "results"
    anomaly = results / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
    prognostics = results / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"
    output = tmp_path / "analysis-report.md"

    exit_code = cli.main(
        [
            "analysis",
            "report",
            "--anomaly",
            str(anomaly),
            "--asset",
            "Bearing1_2",
            "--prognostics",
            str(prognostics),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    rendered = output.read_text(encoding="utf-8")
    assert "# PHM Analysis Report" in rendered
    assert "## Attached prognostics evidence" in rendered
    assert "No operational primary method is asserted" in rendered
    captured = capsys.readouterr().out
    assert f"report: {output}" in captured


def test_analysis_report_cli_rejects_unknown_asset(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = Path(__file__).parents[2]
    anomaly = (
        repository_root
        / "docs"
        / "research"
        / "results"
        / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
    )

    exit_code = cli.main(
        [
            "analysis",
            "report",
            "--anomaly",
            str(anomaly),
            "--asset",
            "Bearing9_9",
            "--output",
            str(tmp_path / "report.md"),
        ]
    )

    assert exit_code == 1
    assert "Bearing9_9" in capsys.readouterr().err
