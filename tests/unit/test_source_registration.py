from datetime import datetime

import pytest

from industrial_phm.application import (
    ChannelSemanticBinding,
    FileSourceConfig,
    FileSourceMode,
    InMemorySourceRepository,
    MeasurementDefinition,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceAlreadyRegisteredError,
    SourceRepository,
    SourceType,
    UnknownRegisteredSourceError,
)
from industrial_phm.connectors import OpcUaNodeMapping


def _registered_source(
    *,
    source_id: str = "field-export:pump-01",
    source_path: str = "data/pump.csv",
) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name="Pump 01 prepared CSV",
        config=FileSourceConfig(
            source_path=source_path,
            asset_id="pump-01",
            measurement_point_id="drive-end-bearing",
            channel_columns=("vibration_x", "temperature"),
            timestamp_column="timestamp",
            sampling_rate_hz=1_000.0,
            sampling_rate_tolerance_ratio=0.05,
            minimum_sample_count=32,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )


def test_file_source_config_preserves_existing_csv_layout_semantics() -> None:
    channels = ["vibration_x", "temperature"]

    config = FileSourceConfig(
        source_path="data/pump.csv",
        asset_id="pump-01",
        measurement_point_id="drive-end-bearing",
        channel_columns=channels,
        timestamp_column="timestamp",
        sampling_rate_hz=1_000.0,
        sampling_rate_tolerance_ratio=0.05,
        minimum_sample_count=32,
    )
    channels.append("rpm")

    layout = config.to_csv_sensor_layout()

    assert config.channel_columns == ("vibration_x", "temperature")
    assert layout.asset_id == "pump-01"
    assert layout.channel_columns == ("vibration_x", "temperature")
    assert layout.timestamp_column == "timestamp"
    assert layout.sampling_rate_hz == 1_000.0
    assert layout.sampling_rate_tolerance_ratio == 0.05
    assert layout.minimum_sample_count == 32


def test_file_source_config_does_not_require_path_to_be_currently_reachable() -> None:
    config = FileSourceConfig(
        source_path="offline/pump.csv",
        asset_id="pump-01",
        channel_columns=("vibration_x",),
        sampling_rate_hz=1_000.0,
    )

    assert config.source_path == "offline/pump.csv"


def test_file_source_config_requires_existing_csv_time_basis() -> None:
    with pytest.raises(ValueError, match="timestamp_column or sampling_rate_hz"):
        FileSourceConfig(
            source_path="data/pump.csv",
            asset_id="pump-01",
            channel_columns=("vibration_x",),
        )


def test_history_directory_registration_requires_explicit_timestamp() -> None:
    with pytest.raises(ValueError, match="explicit timestamp_column"):
        FileSourceConfig(
            source_path="data/history",
            mode=FileSourceMode.HISTORY_DIRECTORY,
            asset_id="pump-01",
            channel_columns=("vibration_x",),
            sampling_rate_hz=1_000.0,
        )


def test_registered_source_preserves_control_plane_identity_without_health_claim() -> None:
    source = _registered_source()

    assert source.source_type == SourceType.FILE
    assert source.source_id == "field-export:pump-01"
    assert source.asset_id == "pump-01"
    assert source.measurement_point_id == "drive-end-bearing"
    assert not hasattr(source, "connected")
    assert not hasattr(source, "healthy")
    assert not hasattr(source, "last_received_at")


def test_registered_source_requires_timezone_aware_registration_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RegisteredSource(
            source_id="field-export:pump-01",
            name="Pump 01 prepared CSV",
            config=FileSourceConfig(
                source_path="data/pump.csv",
                asset_id="pump-01",
                channel_columns=("vibration_x",),
                sampling_rate_hz=1_000.0,
            ),
            registered_at=datetime.fromisoformat("2026-09-23T10:00:00"),
        )


def test_in_memory_source_repository_implements_repository_contract() -> None:
    repository = InMemorySourceRepository()

    assert isinstance(repository, SourceRepository)


def test_in_memory_source_repository_registers_resolves_and_lists_deterministically() -> None:
    repository = InMemorySourceRepository()
    second = _registered_source(
        source_id="source-b",
        source_path="data/b.csv",
    )
    first = _registered_source(
        source_id="source-a",
        source_path="data/a.csv",
    )

    repository.register(second)
    repository.register(first)

    assert repository.get("source-a") is first
    assert repository.list_sources() == (first, second)


def test_in_memory_source_repository_rejects_duplicate_source_id() -> None:
    repository = InMemorySourceRepository()
    repository.register(_registered_source())

    with pytest.raises(SourceAlreadyRegisteredError, match="already registered"):
        repository.register(_registered_source(source_path="data/replacement.csv"))


def test_in_memory_source_repository_rejects_unknown_source_id() -> None:
    repository = InMemorySourceRepository()

    with pytest.raises(UnknownRegisteredSourceError, match="does not exist"):
        repository.get("missing-source")


def test_opcua_source_config_reuses_connector_mapping_contract() -> None:
    first_mapping = OpcUaNodeMapping(
        channel_id="vibration_x",
        node_id="ns=2;s=Machine/VibrationX",
    )
    mappings = [first_mapping]

    config = OpcUaSourceConfig(
        endpoint_url="opc.tcp://plc.example.test:4840",
        asset_id="pump-01",
        measurement_point_id="drive-end-bearing",
        node_mappings=mappings,
        timeout_seconds=2.5,
    )
    mappings.append(
        OpcUaNodeMapping(
            channel_id="temperature",
            node_id="ns=2;s=Machine/Temperature",
        )
    )

    read_config = config.to_opcua_read_config()

    assert config.node_mappings == (first_mapping,)
    assert read_config.endpoint_url == "opc.tcp://plc.example.test:4840"
    assert read_config.node_mappings == (first_mapping,)
    assert read_config.timeout_seconds == 2.5


def test_opcua_source_config_reuses_connector_endpoint_validation() -> None:
    with pytest.raises(ValueError, match=r"opc\.tcp"):
        OpcUaSourceConfig(
            endpoint_url="https://plc.example.test:4840",
            asset_id="pump-01",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
            ),
        )


def test_registered_source_supports_opcua_identity_without_health_claim() -> None:
    source = RegisteredSource(
        source_id="opcua:pump-01",
        name="Pump 01 OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            measurement_point_id="drive-end-bearing",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
            ),
        ),
        registered_at=datetime.fromisoformat("2026-09-23T14:00:00+09:00"),
    )

    assert source.source_type == SourceType.OPCUA
    assert source.asset_id == "pump-01"
    assert source.measurement_point_id == "drive-end-bearing"
    assert not hasattr(source, "connected")
    assert not hasattr(source, "healthy")


def test_in_memory_source_repository_accepts_file_and_opcua_sources() -> None:
    repository = InMemorySourceRepository()
    file_source = _registered_source(source_id="source-file")
    opcua_source = RegisteredSource(
        source_id="source-opcua",
        name="Pump OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
            ),
        ),
        registered_at=datetime.fromisoformat("2026-09-23T14:00:00+09:00"),
    )

    repository.register(opcua_source)
    repository.register(file_source)

    assert repository.list_sources() == (file_source, opcua_source)


def test_opcua_source_config_validates_and_resolves_explicit_semantic_bindings() -> None:
    binding = ChannelSemanticBinding(
        source_id="opcua:pump-01",
        channel_id="vibration_x",
        version="site-a-semantics-v1",
        definition=MeasurementDefinition(
            observed_property="vibration velocity",
            scope="x-axis",
            unit="mm/s",
            unit_evidence="site engineering channel map",
        ),
        interpretation_evidence="site engineering channel map revision 1",
    )
    config = OpcUaSourceConfig(
        endpoint_url="opc.tcp://plc.example.test:4840",
        asset_id="pump-01",
        node_mappings=(
            OpcUaNodeMapping(
                channel_id="vibration_x",
                node_id="ns=2;s=Machine/VibrationX",
            ),
        ),
        semantic_bindings=(binding,),
    )

    assert config.semantic_bindings == (binding,)
    assert config.semantic_binding_for("vibration_x") == binding
    assert config.semantic_binding_for("unknown") is None

    with pytest.raises(ValueError, match="node_mappings"):
        OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
            ),
            semantic_bindings=(
                ChannelSemanticBinding(
                    source_id="opcua:pump-01",
                    channel_id="temperature",
                    version="site-a-semantics-v1",
                    definition=MeasurementDefinition(),
                    interpretation_evidence="unresolved but explicitly versioned mapping",
                ),
            ),
        )

    with pytest.raises(ValueError, match="registered source_id"):
        RegisteredSource(
            source_id="other-source",
            name="Mismatched semantics",
            config=config,
            registered_at=datetime.fromisoformat("2026-09-23T14:00:00+09:00"),
        )
