from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    transition_source_lifecycle,
)
from industrial_phm.cli import main
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import OperationsWorkspace, SqliteCollectionControlRepository

BASE = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


def test_collection_request_cli_updates_desired_state_without_running_collector(
    tmp_path,
    capsys,
) -> None:
    registry_path = tmp_path / "source-registry.json"
    control_path = tmp_path / "collection-control.sqlite"
    repository = JsonSourceRepository(registry_path)
    repository.register(
        RegisteredSource(
            source_id="source-a",
            name="Pump OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="pump-01",
                node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=vibration_x"),),
            ),
            registered_at=BASE,
        )
    )
    transition_source_lifecycle(
        repository,
        "source-a",
        SourceLifecycleState.ACTIVE,
        changed_at=BASE + timedelta(seconds=1),
    )

    exit_code = main(
        [
            "internal",
            "request-collection",
            "--registry",
            str(registry_path),
            "--control-state",
            str(control_path),
            "--source-id",
            "source-a",
            "--state",
            "running",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "desired=running" in output
    record = SqliteCollectionControlRepository(control_path).get("source-a")
    assert record is not None
    assert record.desired_state.value == "running"
    assert record.generation == 1

    exit_code = main(
        [
            "internal",
            "request-collection",
            "--registry",
            str(registry_path),
            "--control-state",
            str(control_path),
            "--source-id",
            "source-a",
            "--state",
            "stopped",
        ]
    )

    assert exit_code == 0
    record = SqliteCollectionControlRepository(control_path).get("source-a")
    assert record is not None
    assert record.desired_state.value == "stopped"
    assert record.generation == 2
    assert repository.get_lifecycle("source-a").state == SourceLifecycleState.ACTIVE


def test_collection_request_cli_accepts_one_workspace_root(tmp_path, capsys) -> None:
    workspace = OperationsWorkspace(tmp_path / "workspace")
    repository = JsonSourceRepository(workspace.source_registry_path)
    repository.register(
        RegisteredSource(
            source_id="source-workspace",
            name="Workspace OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="pump-workspace",
                node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=vibration_x"),),
            ),
            registered_at=BASE,
        )
    )
    transition_source_lifecycle(
        repository,
        "source-workspace",
        SourceLifecycleState.ACTIVE,
        changed_at=BASE + timedelta(seconds=1),
    )

    exit_code = main(
        [
            "internal",
            "request-collection",
            "--workspace",
            str(workspace.root),
            "--source-id",
            "source-workspace",
            "--state",
            "running",
        ]
    )

    assert exit_code == 0
    assert "desired=running" in capsys.readouterr().out
    record = SqliteCollectionControlRepository(workspace.collection_control_path).get(
        "source-workspace"
    )
    assert record is not None
    assert record.desired_state.value == "running"


def test_collection_request_cli_rejects_workspace_mixed_with_explicit_paths(
    tmp_path,
    capsys,
) -> None:
    exit_code = main(
        [
            "internal",
            "request-collection",
            "--workspace",
            str(tmp_path / "workspace"),
            "--registry",
            str(tmp_path / "other.json"),
            "--source-id",
            "source-a",
            "--state",
            "running",
        ]
    )

    assert exit_code == 1
    assert "--workspace cannot be combined" in capsys.readouterr().err
