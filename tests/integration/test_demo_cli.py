from pathlib import Path

import industrial_phm.commands.demo as demo_commands
from industrial_phm.cli import main


def test_demo_synthetic_builds_defaultable_product_preset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}

    def fake_run(preset) -> int:
        captured["preset"] = preset
        return 0

    monkeypatch.setattr(demo_commands, "run_synthetic_demo", fake_run)

    exit_code = main(
        [
            "demo",
            "synthetic",
            "--workspace",
            str(tmp_path / "demo"),
            "--opcua-port",
            "4848",
            "--ui-port",
            "2728",
        ]
    )

    assert exit_code == 0
    preset = captured["preset"]
    assert preset.workspace == tmp_path / "demo"
    assert preset.opcua_port == 4848
    assert preset.ui_port == 2728


def test_demo_synthetic_reports_invalid_port_as_cli_failure(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(
        [
            "demo",
            "synthetic",
            "--workspace",
            str(tmp_path / "demo"),
            "--opcua-port",
            "0",
        ]
    )

    assert exit_code == 1
    assert "opcua_port must be an integer between 1 and 65535" in capsys.readouterr().err
