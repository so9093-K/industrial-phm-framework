import pytest

from industrial_phm.cli import main


def test_doctor_reports_environment_and_next_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "industrial-phm 0.0.1" in output
    assert "python:" in output
    assert "project checkout: detected" in output
    assert "data root:" in output
    assert "research UI runtime:" in output
    assert "deep-learning runtime:" in output
    assert "next:" in output
    assert "marimo run apps/analysis_explorer.py" in output
