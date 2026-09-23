import json
from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceAlreadyRegisteredError,
    SourceFreshnessPolicy,
    SourceFreshnessPolicyRepository,
    SourceLifecycleRecord,
    SourceLifecycleRepository,
    SourceLifecycleState,
    SourceRegistryFormatError,
    SourceRepository,
    UnknownRegisteredSourceError,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping


def _source(
    *,
    source_id: str = "source-a",
    source_path: str = "data/pump.csv",
    mode: FileSourceMode = FileSourceMode.SNAPSHOT,
) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=f"Registered {source_id}",
        config=FileSourceConfig(
            source_path=source_path,
            asset_id="pump-01",
            measurement_point_id="drive-end-bearing",
            channel_columns=("vibration_x", "temperature"),
            mode=mode,
            timestamp_column="timestamp",
            sampling_rate_hz=1_000.0,
            sampling_rate_tolerance_ratio=0.05,
            minimum_sample_count=32,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )


def _opcua_source(*, source_id: str = "opcua-source") -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=f"Registered ${source_id}",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            measurement_point_id="drive-end-bearing",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
                OpcUaNodeMapping(
                    channel_id="temperature",
                    node_id="ns=2;s=Machine/Temperature",
                ),
            ),
            timeout_seconds=2.5,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T14:00:00+09:00"),
    )


def test_json_source_repository_implements_registration_and_lifecycle_contracts(
    tmp_path: Path,
) -> None:
    repository = JsonSourceRepository(tmp_path / "sources.json")

    assert isinstance(repository, SourceRepository)
    assert isinstance(repository, SourceLifecycleRepository)
    assert isinstance(repository, SourceFreshnessPolicyRepository)


def test_json_source_repository_round_trip_survives_new_repository_instance(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "state" / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()

    repository.register(source)

    reopened = JsonSourceRepository(registry)
    assert reopened.get(source.source_id) == source
    assert reopened.list_sources() == (source,)
    assert reopened.get_lifecycle(source.source_id) == SourceLifecycleRecord(
        source_id=source.source_id,
        state=SourceLifecycleState.REGISTERED,
        changed_at=source.registered_at,
    )


def test_json_source_repository_preserves_history_directory_configuration(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    source = _source(
        source_id="history-source",
        source_path="data/history",
        mode=FileSourceMode.HISTORY_DIRECTORY,
    )

    JsonSourceRepository(registry).register(source)
    loaded = JsonSourceRepository(registry).get("history-source")

    assert loaded.config.mode == FileSourceMode.HISTORY_DIRECTORY
    assert loaded.config.source_path == "data/history"
    assert loaded.config.timestamp_column == "timestamp"


def test_json_source_repository_writes_sources_and_lifecycle_in_deterministic_id_order(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)

    repository.register(_source(source_id="source-b", source_path="data/b.csv"))
    repository.register(_source(source_id="source-a", source_path="data/a.csv"))

    payload = json.loads(registry.read_text(encoding="utf-8"))
    source_ids = [item["source_id"] for item in payload["sources"]]
    lifecycle_ids = [item["source_id"] for item in payload["lifecycle"]]

    assert payload["schema"] == "industrial-phm-source-registry-v4"
    assert source_ids == ["source-a", "source-b"]
    assert lifecycle_ids == ["source-a", "source-b"]


def test_json_source_repository_does_not_persist_runtime_health_claims(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"

    JsonSourceRepository(registry).register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    stored_source = payload["sources"][0]
    stored_lifecycle = payload["lifecycle"][0]

    assert set(stored_source) == {
        "source_id",
        "name",
        "source_type",
        "registered_at",
        "config",
    }
    assert set(stored_lifecycle) == {
        "source_id",
        "state",
        "changed_at",
        "detail",
    }
    assert "connected" not in stored_lifecycle
    assert "healthy" not in stored_lifecycle
    assert "last_received_at" not in stored_lifecycle
    assert payload["freshness_policies"] == []
    assert "received_at" not in payload
    assert "last_received_at" not in payload


def test_json_source_repository_persists_valid_lifecycle_transition(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)

    transitioned = transition_source_lifecycle(
        repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    reopened = JsonSourceRepository(registry)
    assert reopened.get_lifecycle(source.source_id) == transitioned
    assert reopened.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_json_source_repository_reads_v1_as_implicit_registered_and_upgrades_on_write(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)

    payload = json.loads(registry.read_text(encoding="utf-8"))
    legacy_payload = {
        "schema": "industrial-phm-source-registry-v1",
        "sources": payload["sources"],
    }
    registry.write_text(json.dumps(legacy_payload), encoding="utf-8")

    reopened = JsonSourceRepository(registry)
    assert reopened.get_lifecycle(source.source_id).state == SourceLifecycleState.REGISTERED

    transition_source_lifecycle(
        reopened,
        source.source_id,
        SourceLifecycleState.PAUSED,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    upgraded = json.loads(registry.read_text(encoding="utf-8"))
    assert upgraded["schema"] == "industrial-phm-source-registry-v4"
    assert upgraded["lifecycle"][0]["state"] == "paused"


def test_json_source_repository_reads_v3_file_registry_and_upgrades_on_write(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)

    payload = json.loads(registry.read_text(encoding="utf-8"))
    legacy_v3 = dict(payload)
    legacy_v3["schema"] = "industrial-phm-source-registry-v3"
    registry.write_text(json.dumps(legacy_v3), encoding="utf-8")

    reopened = JsonSourceRepository(registry)
    assert reopened.get(source.source_id) == source

    reopened.set_freshness_policy(
        SourceFreshnessPolicy(
            source_id=source.source_id,
            max_observation_age_seconds=60.0,
            changed_at=datetime.fromisoformat("2026-09-23T10:06:00+09:00"),
        )
    )

    upgraded = json.loads(registry.read_text(encoding="utf-8"))
    assert upgraded["schema"] == "industrial-phm-source-registry-v4"


def test_json_source_repository_reads_v2_without_freshness_policy_and_upgrades_on_policy_write(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)

    payload = json.loads(registry.read_text(encoding="utf-8"))
    legacy_v2 = {
        "schema": "industrial-phm-source-registry-v2",
        "sources": payload["sources"],
        "lifecycle": payload["lifecycle"],
    }
    registry.write_text(json.dumps(legacy_v2), encoding="utf-8")

    reopened = JsonSourceRepository(registry)
    assert reopened.get_freshness_policy(source.source_id) is None

    policy = SourceFreshnessPolicy(
        source_id=source.source_id,
        max_observation_age_seconds=300.0,
        changed_at=datetime.fromisoformat("2026-09-23T10:06:00+09:00"),
    )
    reopened.set_freshness_policy(policy)

    upgraded = json.loads(registry.read_text(encoding="utf-8"))
    assert upgraded["schema"] == "industrial-phm-source-registry-v4"
    assert upgraded["freshness_policies"][0]["source_id"] == source.source_id
    assert upgraded["freshness_policies"][0]["max_observation_age_seconds"] == 300.0


def test_json_source_repository_writes_freshness_policies_in_source_id_order(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source(source_id="source-b", source_path="data/b.csv"))
    repository.register(_source(source_id="source-a", source_path="data/a.csv"))

    repository.set_freshness_policy(
        SourceFreshnessPolicy(
            source_id="source-b",
            max_observation_age_seconds=120.0,
            changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
        )
    )
    repository.set_freshness_policy(
        SourceFreshnessPolicy(
            source_id="source-a",
            max_observation_age_seconds=60.0,
            changed_at=datetime.fromisoformat("2026-09-23T10:06:00+09:00"),
        )
    )

    payload = json.loads(registry.read_text(encoding="utf-8"))

    assert [item["source_id"] for item in payload["freshness_policies"]] == [
        "source-a",
        "source-b",
    ]


def test_json_source_repository_persists_and_clears_freshness_policy(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)
    policy = SourceFreshnessPolicy(
        source_id=source.source_id,
        max_observation_age_seconds=120.0,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    repository.set_freshness_policy(policy)

    reopened = JsonSourceRepository(registry)
    assert reopened.get_freshness_policy(source.source_id) == policy

    reopened.clear_freshness_policy(source.source_id)
    assert JsonSourceRepository(registry).get_freshness_policy(source.source_id) is None


def test_json_source_repository_rejects_freshness_policy_for_unknown_source(
    tmp_path: Path,
) -> None:
    repository = JsonSourceRepository(tmp_path / "sources.json")
    policy = SourceFreshnessPolicy(
        source_id="missing-source",
        max_observation_age_seconds=60.0,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.get_freshness_policy("missing-source")

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.set_freshness_policy(policy)

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.clear_freshness_policy("missing-source")


def test_json_source_repository_rejects_freshness_policy_time_regression(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)
    repository.set_freshness_policy(
        SourceFreshnessPolicy(
            source_id=source.source_id,
            max_observation_age_seconds=120.0,
            changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
        )
    )

    with pytest.raises(ValueError, match="must not move backwards"):
        repository.set_freshness_policy(
            SourceFreshnessPolicy(
                source_id=source.source_id,
                max_observation_age_seconds=60.0,
                changed_at=datetime.fromisoformat("2026-09-23T10:04:59+09:00"),
            )
        )


def test_json_source_repository_rejects_duplicate_without_replacing_existing_source(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    original = _source()

    repository.register(original)

    with pytest.raises(SourceAlreadyRegisteredError, match="already registered"):
        repository.register(_source(source_path="data/replacement.csv"))

    assert JsonSourceRepository(registry).get(original.source_id) == original


def test_json_source_repository_rejects_unknown_source_id(tmp_path: Path) -> None:
    repository = JsonSourceRepository(tmp_path / "sources.json")

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.get("missing-source")

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.get_lifecycle("missing-source")


def test_json_source_repository_rejects_malformed_json(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    registry.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="valid JSON"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    registry.write_text(
        json.dumps({"schema": "future-schema", "sources": []}),
        encoding="utf-8",
    )

    with pytest.raises(SourceRegistryFormatError, match="unsupported source registry schema"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_unknown_source_type(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["sources"][0]["source_type"] = "mqtt"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="source_type is unsupported"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_duplicate_ids_in_persisted_registry(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["sources"].append(dict(payload["sources"][0]))
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="duplicate source_id"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_duplicate_lifecycle_ids(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["lifecycle"].append(dict(payload["lifecycle"][0]))
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="duplicate lifecycle source_id"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_lifecycle_source_alignment_drift(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["lifecycle"] = []
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="lifecycle IDs do not match"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_unvalidated_direct_lifecycle_jump(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)

    with pytest.raises(ValueError, match="invalid source lifecycle transition"):
        repository.set_lifecycle(
            SourceLifecycleRecord(
                source_id=source.source_id,
                state=SourceLifecycleState.ERROR,
                changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
                detail="cannot jump directly from registered to error",
            )
        )


def test_json_source_repository_rejects_duplicate_freshness_policy_ids(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _source()
    repository.register(source)
    repository.set_freshness_policy(
        SourceFreshnessPolicy(
            source_id=source.source_id,
            max_observation_age_seconds=120.0,
            changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
        )
    )

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["freshness_policies"].append(dict(payload["freshness_policies"][0]))
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="duplicate freshness-policy source_id"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_rejects_freshness_policy_for_unregistered_source(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["freshness_policies"] = [
        {
            "source_id": "missing-source",
            "max_observation_age_seconds": 60.0,
            "changed_at": "2026-09-23T10:05:00+09:00",
        }
    ]
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="unregistered sources"):
        JsonSourceRepository(registry).list_sources()


def test_json_source_repository_round_trips_opcua_source_config(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    source = _opcua_source()

    repository.register(source)

    reopened = JsonSourceRepository(registry)
    loaded = reopened.get(source.source_id)

    assert loaded == source
    assert loaded.source_type.value == "opcua"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    assert payload["schema"] == "industrial-phm-source-registry-v4"
    assert payload["sources"][0]["config"] == {
        "asset_id": "pump-01",
        "endpoint_url": "opc.tcp://plc.example.test:4840",
        "measurement_point_id": "drive-end-bearing",
        "node_mappings": [
            {
                "channel_id": "vibration_x",
                "node_id": "ns=2;s=Machine/VibrationX",
            },
            {
                "channel_id": "temperature",
                "node_id": "ns=2;s=Machine/Temperature",
            },
        ],
        "timeout_seconds": 2.5,
    }


def test_v3_registry_rejects_opcua_source_type_as_schema_incompatible(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    repository = JsonSourceRepository(registry)
    repository.register(_opcua_source())

    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["schema"] = "industrial-phm-source-registry-v3"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceRegistryFormatError, match="unsupported by this registry schema"):
        JsonSourceRepository(registry).list_sources()

