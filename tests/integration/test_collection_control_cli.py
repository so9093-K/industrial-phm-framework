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
from industrial_phm.runtime import SqliteCollectionControlRepository

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
            "operations",
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
            "operations",
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
