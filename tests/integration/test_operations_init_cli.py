from pathlib import Path

from industrial_phm.cli import main
from industrial_phm.runtime import OPERATIONS_CONFIG_SCHEMA, OperationsWorkspace


def test_operations_init_creates_minimal_versioned_workspace(tmp_path: Path, capsys) -> None:
    root = tmp_path / "plant-a"
    workspace = OperationsWorkspace(root)

    exit_code = main(["operations", "init", str(root)])

    assert exit_code == 0
    config_text = workspace.config_path.read_text(encoding="utf-8")
    assert config_text.startswith(f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n')
    assert "[collection]" in config_text
    assert "[analysis]" in config_text
    assert workspace.history_data_path.is_dir()
    assert workspace.logs_path.is_dir()
    assert not workspace.source_registry_path.exists()
    assert not workspace.collection_control_path.exists()
    output = capsys.readouterr().out
    assert "state=created" in output
    assert f"workspace={root}" in output


def test_operations_init_is_idempotent_for_valid_workspace(tmp_path: Path, capsys) -> None:
    root = tmp_path / "plant-a"

    assert main(["operations", "init", str(root)]) == 0
    capsys.readouterr()

    assert main(["operations", "init", str(root)]) == 0

    assert "state=existing" in capsys.readouterr().out


def test_operations_init_refuses_non_empty_uninitialized_directory(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    (root / "unrelated.txt").write_text("keep", encoding="utf-8")

    exit_code = main(["operations", "init", str(root)])

    assert exit_code == 1
    assert "refusing to initialize a non-empty Operations workspace" in capsys.readouterr().err
    assert (root / "unrelated.txt").read_text(encoding="utf-8") == "keep"
    assert not (root / "config.toml").exists()


def test_operations_init_rejects_invalid_existing_config(tmp_path: Path, capsys) -> None:
    root = tmp_path / "invalid"
    root.mkdir()
    (root / "config.toml").write_text('schema = "future"\n', encoding="utf-8")

    exit_code = main(["operations", "init", str(root)])

    assert exit_code == 1
    assert "unsupported Operations config schema" in capsys.readouterr().err
