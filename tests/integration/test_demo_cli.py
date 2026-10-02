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



def test_demo_aihub_boiler_builds_recorded_data_preset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}

    def fake_run(preset) -> int:
        captured["preset"] = preset
        return 0

    monkeypatch.setattr(demo_commands, "run_aihub_boiler_demo", fake_run)
    archive = tmp_path / "boiler.zip"

    exit_code = main(
        [
            "demo",
            "aihub-boiler",
            "--archive",
            str(archive),
            "--workspace",
            str(tmp_path / "demo"),
            "--opcua-port",
            "4858",
            "--ui-port",
            "2738",
            "--speed",
            "120",
        ]
    )

    assert exit_code == 0
    preset = captured["preset"]
    assert preset.archive == archive
    assert preset.workspace == tmp_path / "demo"
    assert preset.opcua_port == 4858
    assert preset.ui_port == 2738
    assert preset.speed == 120.0


def test_demo_aihub_boiler_reports_invalid_speed_as_cli_failure(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(
        [
            "demo",
            "aihub-boiler",
            "--archive",
            str(tmp_path / "boiler.zip"),
            "--speed",
            "0",
        ]
    )

    assert exit_code == 1
    assert "speed must be a positive number" in capsys.readouterr().err
