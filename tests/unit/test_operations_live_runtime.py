from datetime import UTC, datetime, timedelta

from industrial_phm.application.asset_history import (
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
)
from industrial_phm.application.measurement_history import (
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
)
from industrial_phm.application.operations_assets import AssetWorkspaceSource
from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    RegisteredSource,
    SourceType,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import operations_live as operations_live_module
from industrial_phm.runtime.operations_app_wiring import resolve_operations_app_paths
from industrial_phm.runtime.operations_live import load_operations_live_observation

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
RECORDED_AT = datetime(2020, 11, 14, 6, 30, tzinfo=UTC)


def _source() -> RegisteredSource:
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


def _workspace_source() -> AssetWorkspaceSource:
    source = _source()
    return AssetWorkspaceSource(
        source_id=source.source_id,
        name=source.name,
        source_type=SourceType.OPCUA,
        status=OperationsMonitorStatus.RUNNING,
        last_data_at=NOW,
        measurement_point_id=source.measurement_point_id,
        channel_count=1,
    )


def _point() -> MeasurementHistoryPoint:
    return MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id="raw-live",
            source_id="source-live",
            source_type=SourceType.OPCUA,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="current-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=RECORDED_AT,
            value=18.2,
            status_good=True,
            ingestion_mode=HistoryIngestionMode.REPLAY,
        ),
        conflicting_duplicate=False,
    )


def test_live_loader_keeps_mapped_source_visible_before_history_exists(tmp_path) -> None:
    paths = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "workspace")}
    )

    view = load_operations_live_observation(
        paths,
        asset_id="boiler-01",
        channel_id="current-r",
        registered_sources=(_source(),),
        asset_sources=(_workspace_source(),),
        sampled_at=NOW,
    )

    assert len(view.series) == 1
    assert view.series[0].source_id == "source-live"
    assert view.series[0].latest_point is None
    assert view.series[0].last_received_at is None


def test_live_loader_anchors_recent_window_to_recorded_event_time(tmp_path, monkeypatch) -> None:
    paths = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "workspace")}
    )
    paths.workspace.root.mkdir(parents=True, exist_ok=True)
    paths.history_catalog.touch()
    point = _point()
    queries = []

    class _FakeHistory:
        def __init__(self, config):
            self.config = config

        def query_latest_measurements(self, asset_id, *, channel_id):
            assert asset_id == "boiler-01"
            assert channel_id == "current-r"
            return (point,)

        def query_measurement_page(
            self,
            asset_id,
            *,
            start_at,
            end_at,
            channel_id,
            point_budget,
            latest,
        ):
            queries.append((start_at, end_at, point_budget, latest))
            return MeasurementHistoryPage((point,), False, point_budget)

    monkeypatch.setattr(operations_live_module, "DuckLakeAssetHistory", _FakeHistory)

    view = load_operations_live_observation(
        paths,
        asset_id="boiler-01",
        channel_id="current-r",
        registered_sources=(_source(),),
        asset_sources=(_workspace_source(),),
        sampled_at=NOW,
        lookback_seconds=60,
        point_budget=120,
    )

    assert view.series[0].latest_point == point
    assert queries == [
        (
            RECORDED_AT - timedelta(seconds=60) + timedelta(microseconds=1),
            RECORDED_AT + timedelta(microseconds=1),
            120,
            True,
        )
    ]
