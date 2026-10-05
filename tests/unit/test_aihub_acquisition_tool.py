import importlib.util
import os
import sys
from pathlib import Path

import pytest

_TOOL_PATH = Path(__file__).resolve().parents[2] / "tools" / "aihub" / "cli.py"
_TOOL_SPEC = importlib.util.spec_from_file_location("aihub_acquisition_cli", _TOOL_PATH)
assert _TOOL_SPEC is not None
assert _TOOL_SPEC.loader is not None
aihub_cli = importlib.util.module_from_spec(_TOOL_SPEC)
sys.modules[_TOOL_SPEC.name] = aihub_cli
_TOOL_SPEC.loader.exec_module(aihub_cli)

SAMPLE_TREE = """
==========================================
aihubshell version 25.09.19 v0.6
==========================================
    └─149.전력 설비 에너지 품질
        └─01.데이터
            ├─1.Training
            │  ├─라벨링데이터
            │  │  └─5.보일러.zip | 313 MB | 44023
            │  └─원천데이터
            │      ├─5.보일러.zip | 59 MB | 44033
            │      └─7.압출기.zip | 97 MB | 44035
            └─2.Validation
                └─원천데이터
                    └─5.보일러.zip | 8 MB | 44053
"""


def test_inventory_parser_preserves_filekey_split_role_and_rounded_size() -> None:
    files = aihub_cli.parse_inventory(SAMPLE_TREE, dataset_key=239)

    assert [(item.filekey, item.split, item.role) for item in files] == [
        (44023, "training", "label"),
        (44033, "training", "raw"),
        (44035, "training", "raw"),
        (44053, "validation", "raw"),
    ]
    boiler = files[1]
    assert boiler.equipment_group == "보일러"
    assert boiler.declared_size == "59 MB"
    assert boiler.declared_size_bytes_approx == 59 * 1024**2


def test_inventory_parser_rejects_duplicate_filekeys() -> None:
    duplicate = SAMPLE_TREE.replace(
        "7.압출기.zip | 97 MB | 44035",
        "7.압출기.zip | 97 MB | 44033",
    )

    with pytest.raises(aihub_cli.AIHubToolError, match="duplicate filekeys"):
        aihub_cli.parse_inventory(duplicate, dataset_key=239)


def test_bootstrap_plan_is_offline_and_selects_two_training_raw_archives(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert aihub_cli.main(["plan", "239", "--preset", "bootstrap", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "44033" in output
    assert "보일러" in output
    assert "44035" in output
    assert "압출기" in output
    assert "156.0 MiB" in output
    assert "no network request was made" in output


def test_single_archive_preset_can_plan_existing_boiler_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert aihub_cli.main(["plan", "239", "--preset", "boiler", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "44033" in output
    assert "보일러" in output
    assert "44035" not in output


def test_dataset_239_catalog_lists_every_observed_file_separately_from_presets() -> None:
    raw = aihub_cli._read_preset(239)
    files = [aihub_cli._parse_preset_file(item) for item in raw["files"]]
    split_dirs = {"training": "1.Training", "validation": "2.Validation"}
    role_dirs = {"raw": "원천데이터", "label": "라벨링데이터"}

    assert len(files) == raw["observed_inventory"]["observed_file_count"] == 40
    assert len({item.filekey for item in files}) == 40
    assert {(item.equipment_group, item.split, item.role) for item in files} == {
        (group, split, role)
        for group in {item.equipment_group for item in files}
        for split in split_dirs
        for role in role_dirs
    }
    assert len({item.equipment_group for item in files}) == 10
    for item in files:
        assert item.remote_path.endswith(
            f"/{split_dirs[item.split]}/{role_dirs[item.role]}/{item.archive_name}"
        )

    catalog_keys = {item.filekey for item in files}
    presets = raw["presets"]
    assert all(set(keys) <= catalog_keys for keys in presets.values())
    assert len(set().union(*map(set, presets.values()))) < len(catalog_keys)


def test_reference_candidate_plan_selects_only_validation_raw_archives(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        aihub_cli.main(
            ["plan", "239", "--preset", "reference-candidates-validation", "--root", str(tmp_path)]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "44051  validation/raw  공기압축기  57 MB" in output
    assert "44049  validation/raw  펌프_일반모터  57 MB" in output
    assert "보일러" not in output
    assert "압출기" not in output
    assert "114.0 MiB" in output


def test_download_uses_required_auth_argument_and_preserves_archive_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = tmp_path / "arguments.txt"
    fake_shell = tmp_path / "aihubshell"
    fake_shell.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {arguments!s}\nexit 7\n",
        encoding="utf-8",
    )
    fake_shell.chmod(0o755)

    archive = tmp_path / "aihub" / "239" / "archives" / "training" / "raw" / "5.보일러.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"existing-archive")

    monkeypatch.setenv("AIHUBSHELL_PATH", str(fake_shell))
    monkeypatch.setenv("AIHUB_APIKEY", "test-key")

    assert (
        aihub_cli.main(
            [
                "download",
                "239",
                "--preset",
                "boiler",
                "--root",
                str(tmp_path),
                "--force",
            ]
        )
        == 1
    )
    assert arguments.read_text(encoding="utf-8").splitlines() == [
        "-mode",
        "d",
        "-datasetkey",
        "239",
        "-filekey",
        "44033",
        "-aihubapikey",
        "test-key",
    ]
    assert archive.read_bytes() == b"existing-archive"


def test_local_env_does_not_override_explicit_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "AIHUB_APIKEY=from-file\nAIHUBSHELL_PATH='/tmp/aihubshell'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIHUB_APIKEY", "from-process")
    monkeypatch.delenv("AIHUBSHELL_PATH", raising=False)

    aihub_cli.load_local_env(env_path)

    assert os.environ["AIHUB_APIKEY"] == "from-process"
    assert os.environ["AIHUBSHELL_PATH"] == "/tmp/aihubshell"


def test_download_without_api_key_fails_before_running_remote_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_shell = tmp_path / "aihubshell"
    fake_shell.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_shell.chmod(0o755)

    # A developer's real .env must not supply the intentionally missing key.
    monkeypatch.setattr(aihub_cli, "load_local_env", lambda: None)
    monkeypatch.setenv("AIHUBSHELL_PATH", str(fake_shell))
    monkeypatch.delenv("AIHUB_APIKEY", raising=False)

    assert aihub_cli.main(["download", "239", "--root", str(tmp_path)]) == 1
    assert "AIHUB_APIKEY is required" in capsys.readouterr().err
