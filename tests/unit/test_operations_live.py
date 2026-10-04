from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFlowTelemetry,
    AcquisitionSessionTelemetry,
    AcquisitionSpoolTelemetrySnapshot,
    AcquisitionTelemetrySnapshot,
    AcquisitionTelemetrySurface,
)
from industrial_phm.application.asset_history import (
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
)
from industrial_phm.application.measurement_history import (
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_assets import AssetWorkspaceSource
from industrial_phm.application.operations_live import build_live_observation_view
from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceType,
)
from industrial_phm.connectors import OpcUaNodeMapping

NOW = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)


def _opcua_source() -> RegisteredSource:
    return RegisteredSource(
        source_id="source-live",
        name="Boiler live OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="current-r",
                    node_id="ns=2;s=Boiler/CurrentR",
                ),
            ),
        ),
        registered_at=NOW - timedelta(days=1),
    )


def _file_source() -> RegisteredSource:
    return RegisteredSource(
        source_id="source-file",
        name="Boiler archive",
        config=FileSourceConfig(
            source_path="archive.csv",
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_columns=("current-r",),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW - timedelta(days=2),
    )


def _point(
    *,
    source_id: str = "source-live",
    source_type: SourceType = SourceType.OPCUA,
    event_at: datetime,
    value: float,
) -> MeasurementHistoryPoint:
    return MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id=f"raw-{source_id}-{event_at.timestamp()}",
            source_id=source_id,
            source_type=source_type,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="current-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=event_at,
            value=value,
            status_good=True,
            ingestion_mode=(
                HistoryIngestionMode.LIVE
                if source_type == SourceType.OPCUA
                else HistoryIngestionMode.IMPORT
            ),
        ),
        conflicting_duplicate=False,
    )


def _surface() -> AcquisitionTelemetrySurface:
    flow = AcquisitionFlowTelemetry(
        source_id="source-live",
        worker_started_at=NOW - timedelta(seconds=10),
        accepted_event_count=10,
        replayed_event_count=0,
        bad_status_event_count=0,
        updated_at=NOW - timedelta(seconds=1),
        last_delivery_identity=("source-live", 1, 9),
        last_source_timestamp=NOW - timedelta(seconds=2),
        last_received_at=NOW - timedelta(seconds=1),
        last_ingested_at=NOW - timedelta(milliseconds=500),
    )
    return AcquisitionTelemetrySurface(
        source=AcquisitionTelemetrySnapshot(
            source_id="source-live",
            session=AcquisitionSessionTelemetry(
                source_id="source-live",
                worker_started_at=NOW - timedelta(seconds=10),
                state=OpcUaPersistentSessionState.CONNECTED,
                state_changed_at=NOW - timedelta(seconds=5),
                connection_epoch=1,
                reconnect_attempt_index=0,
                callback_queue_overflow_count=0,
                connected_since=NOW - timedelta(seconds=5),
            ),
            flow=flow,
        ),
        spool=AcquisitionSpoolTelemetrySnapshot(
            sampled_at=NOW,
            pending_event_count=0,
            payload_bytes=0,
            oldest_accepted_at=None,
        ),
    )


def test_live_observation_projects_only_mapped_opcua_sources() -> None:
    live_source = _opcua_source()
    file_source = _file_source()
    workspace_source = AssetWorkspaceSource(
        source_id=live_source.source_id,
        name=live_source.name,
        source_type=SourceType.OPCUA,
        status=OperationsMonitorStatus.RUNNING,
        last_data_at=NOW - timedelta(seconds=1),
        measurement_point_id="panel-main",
        channel_count=1,
    )
    first = _point(event_at=NOW - timedelta(seconds=3), value=18.1)
    latest = _point(event_at=NOW - timedelta(seconds=2), value=18.2)

    view = build_live_observation_view(
        asset_id="boiler-01",
        channel_id="current-r",
        registered_sources=(file_source, live_source),
        asset_sources=(workspace_source,),
        acquisition_surfaces=(_surface(),),
        latest_points=(latest,),
        recent_page=MeasurementHistoryPage(
            points=(first, latest),
            truncated=False,
            point_budget=120,
        ),
        sampled_at=NOW,
    )

    assert len(view.series) == 1
    series = view.series[0]
    assert series.source_id == "source-live"
    assert series.status == OperationsMonitorStatus.RUNNING
    assert series.session_state == OpcUaPersistentSessionState.CONNECTED
    assert series.latest_point == latest
    assert series.recent_points == (first, latest)
    assert series.last_received_at == NOW - timedelta(seconds=1)
    assert series.last_source_timestamp == NOW - timedelta(seconds=2)
    assert series.average_event_rate_hz == 1.0
    assert view.latest_received_at == NOW - timedelta(seconds=1)
    assert view.point_budget == 120
    assert view.truncated is False


def test_live_observation_does_not_invent_live_series_for_file_history() -> None:
    point = _point(
        source_id="source-file",
        source_type=SourceType.FILE,
        event_at=NOW - timedelta(hours=1),
        value=17.0,
    )

    view = build_live_observation_view(
        asset_id="boiler-01",
        channel_id="current-r",
        registered_sources=(_file_source(),),
        asset_sources=(),
        acquisition_surfaces=(),
        latest_points=(point,),
        recent_page=MeasurementHistoryPage(
            points=(point,),
            truncated=False,
            point_budget=20,
        ),
        sampled_at=NOW,
    )

    assert view.series == ()
    assert view.latest_received_at is None


def test_live_observation_rejects_measurements_from_another_channel() -> None:
    live_source = _opcua_source()
    workspace_source = AssetWorkspaceSource(
        source_id=live_source.source_id,
        name=live_source.name,
        source_type=SourceType.OPCUA,
        status=OperationsMonitorStatus.RUNNING,
        last_data_at=NOW,
        measurement_point_id="panel-main",
        channel_count=1,
    )
    wrong = MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id="raw-other",
            source_id=live_source.source_id,
            source_type=SourceType.OPCUA,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="voltage-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=NOW,
            value=230.0,
            status_good=True,
            ingestion_mode=HistoryIngestionMode.LIVE,
        ),
        conflicting_duplicate=False,
    )

    with pytest.raises(ValueError, match="asset_id and channel_id"):
        build_live_observation_view(
            asset_id="boiler-01",
            channel_id="current-r",
            registered_sources=(live_source,),
            asset_sources=(workspace_source,),
            acquisition_surfaces=(_surface(),),
            latest_points=(wrong,),
            recent_page=MeasurementHistoryPage(
                points=(),
                truncated=False,
                point_budget=20,
            ),
            sampled_at=NOW,
        )
