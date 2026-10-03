import os
import socket
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application import JsonWindowAnalysisRuntimeRepository
from industrial_phm.cli import main
from industrial_phm.runtime import (
    OPERATIONS_CONFIG_SCHEMA,
    OperationsChildProcessState,
    OperationsComponentKind,
    OperationsRuntimeConfig,
    OperationsSupervisorState,
    OperationsSupervisorStateKind,
    OperationsSupervisorStateRepository,
    OperationsUiConfig,
    OperationsWorkspace,
    SqliteAcquisitionTelemetryRepository,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config


def test_operations_init_creates_minimal_versioned_workspace(tmp_path: Path, capsys) -> None:
    root = tmp_path / "plant-a"
    workspace = OperationsWorkspace(root)

    exit_code = main(["operations", "init", str(root)])

    assert exit_code == 0
    config_text = workspace.config_path.read_text(encoding="utf-8")
    assert config_text.startswith(f'schema = "{OPERATIONS_CONFIG_SCHEMA}"\n')
    assert "[collection]" in config_text
    assert "[analysis]" in config_text
    assert "[ui]" in config_text
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


def test_operations_init_rejects_v1_workspace_config(tmp_path: Path, capsys) -> None:
    root = tmp_path / "plant-a"
    root.mkdir()
    config_path = root / "config.toml"
    config_path.write_text(
        'schema = "industrial-phm-operations-runtime-v1"\n',
        encoding="utf-8",
    )

    exit_code = main(["operations", "init", str(root)])

    assert exit_code == 1
    assert "unsupported Operations config schema" in capsys.readouterr().err
    assert config_path.read_text(encoding="utf-8") == (
        'schema = "industrial-phm-operations-runtime-v1"\n'
    )


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


def test_operations_status_reports_unavailable_initialized_workspace(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "plant-a"
    assert main(["operations", "init", str(root)]) == 0
    capsys.readouterr()

    exit_code = main(["operations", "status", str(root)])

    assert exit_code == 2
    output = capsys.readouterr().out
    assert f"workspace={root} ready=no" in output
    assert "supervisor condition=unavailable" in output
    assert "collection condition=unavailable" in output
    assert "analysis condition=unavailable" in output
    assert "ui condition=unavailable" in output


def test_operations_status_reports_ready_from_process_and_component_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "plant-a"
    workspace = OperationsWorkspace(root)
    assert main(["operations", "init", str(root)]) == 0
    capsys.readouterr()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        write_operations_runtime_config(
            workspace.config_path,
            OperationsRuntimeConfig(ui=OperationsUiConfig(port=port)),
        )

        at = datetime.now(UTC)
        pid = os.getpid()
        OperationsSupervisorStateRepository(workspace.supervisor_state_path).write(
            OperationsSupervisorState(
                state=OperationsSupervisorStateKind.RUNNING,
                supervisor_pid=pid,
                started_at=at,
                updated_at=at,
                components=(
                    OperationsChildProcessState(
                        OperationsComponentKind.COLLECTION,
                        pid,
                        workspace.logs_path / "collection.log",
                    ),
                    OperationsChildProcessState(
                        OperationsComponentKind.ANALYSIS,
                        pid,
                        workspace.logs_path / "analysis.log",
                    ),
                    OperationsChildProcessState(
                        OperationsComponentKind.UI,
                        pid,
                        workspace.logs_path / "ui.log",
                    ),
                ),
            )
        )
        telemetry = SqliteAcquisitionTelemetryRepository(workspace.acquisition_telemetry_path)
        telemetry.record_collection_service_start(started_at=at)
        JsonWindowAnalysisRuntimeRepository(workspace.analysis_runtime_path).record_start(at)

        exit_code = main(["operations", "status", str(root)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"workspace={root} ready=yes" in output
    assert "supervisor condition=running" in output
    assert "collection condition=running" in output
    assert "runtime=running" in output
    assert "analysis condition=running" in output
    assert "ui condition=running" in output
    assert "runtime=listener-ready" in output
