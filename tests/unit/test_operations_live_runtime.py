from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.asset_history import (
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
)
from industrial_phm.application.measurement_history import (
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
    MultiSignalMeasurementHistoryAggregation,
)
from industrial_phm.application.operations_assets import AssetWorkspaceSource
from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceType,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import operations_live
from industrial_phm.runtime.operations_app_wiring import resolve_operations_app_paths

NOW = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)
REPLAY_EVENT = datetime(2021, 7, 1, 1, 2, 3, tzinfo=UTC)


def _point(
    *,
    source_id: str,
    source_type: SourceType,
    event_at: datetime,
    value: float,
    ingestion_mode: HistoryIngestionMode,
) -> MeasurementHistoryPoint:
    return MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id=f"raw-{source_id}",
            source_id=source_id,
            source_type=source_type,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="current-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=event_at,
            value=value,
            status_good=True,
            ingestion_mode=ingestion_mode,
        ),
        conflicting_duplicate=False,
    )


def _live_source() -> RegisteredSource:
    return RegisteredSource(
        source_id="live-opcua",
        name="Replay OPC UA",
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
        source_id="archive-file",
        name="Archive",
        config=FileSourceConfig(
            source_path="archive.csv",
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_columns=("current-r",),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW - timedelta(days=2),
    )


def test_live_loader_anchors_recent_window_to_mapped_live_source(
    tmp_path,
    monkeypatch,
) -> None:
    paths = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "workspace")}
    )
    paths.history_catalog.parent.mkdir(parents=True, exist_ok=True)
    paths.history_catalog.touch()

    live_point = _point(
        source_id="live-opcua",
        source_type=SourceType.OPCUA,
        event_at=REPLAY_EVENT,
        value=18.2,
        ingestion_mode=HistoryIngestionMode.REPLAY,
    )
    newer_file_point = _point(
        source_id="archive-file",
        source_type=SourceType.FILE,
        event_at=NOW - timedelta(minutes=1),
        value=99.0,
        ingestion_mode=HistoryIngestionMode.IMPORT,
    )
    query: dict[str, datetime] = {}

    class _FakeHistory:
        def __init__(self, _config) -> None:
            pass

        def query_latest_measurements(self, _asset_id, *, channel_id):
            assert channel_id == "current-r"
            return newer_file_point, live_point

        def query_measurement_page(
            self,
            _asset_id,
            *,
            start_at,
            end_at,
            channel_id,
            point_budget,
            latest,
        ):
            assert channel_id == "current-r"
            assert point_budget == operations_live.DEFAULT_LIVE_POINT_BUDGET
            assert latest is True
            query["start_at"] = start_at
            query["end_at"] = end_at
            return MeasurementHistoryPage((live_point,), False, point_budget)

    monkeypatch.setattr(operations_live, "DuckLakeAssetHistory", _FakeHistory)

    source = _live_source()
    view = operations_live.load_operations_live_observation(
        paths,
        asset_id="boiler-01",
        channel_id="current-r",
        registered_sources=(_file_source(), source),
        asset_sources=(
            AssetWorkspaceSource(
                source_id=source.source_id,
                name=source.name,
                source_type=SourceType.OPCUA,
                status=OperationsMonitorStatus.RUNNING,
                last_data_at=NOW,
                measurement_point_id="panel-main",
                channel_count=1,
            ),
        ),
        sampled_at=NOW,
    )

    expected_end = REPLAY_EVENT + timedelta(microseconds=1)
    assert query["end_at"] == expected_end
    assert query["start_at"] == expected_end - timedelta(
        seconds=operations_live.DEFAULT_LIVE_LOOKBACK_SECONDS
    )
    assert view.series[0].latest_point == live_point


def test_history_read_boundary_wraps_expected_storage_failure_only() -> None:
    class _ExpectedFailureHistory:
        def list_history_channels(self, _asset_id):
            raise OSError("catalog unavailable")

    with pytest.raises(operations_live.OperationsReadError, match="catalog unavailable"):
        operations_live.list_operations_history_channels(
            _ExpectedFailureHistory(),
            "boiler-01",
        )

    class _ProgrammerFailureHistory:
        def list_history_channels(self, _asset_id):
            raise AssertionError("history invariant broken")

    with pytest.raises(AssertionError, match="history invariant broken"):
        operations_live.list_operations_history_channels(
            _ProgrammerFailureHistory(),
            "boiler-01",
        )


def test_multi_signal_latest_read_uses_one_bounded_asset_query() -> None:
    point = _point(
        source_id="live-opcua",
        source_type=SourceType.OPCUA,
        event_at=REPLAY_EVENT,
        value=18.2,
        ingestion_mode=HistoryIngestionMode.REPLAY,
    )
    calls: list[tuple[str, int]] = []

    class _History:
        def query_latest_asset_measurements(self, asset_id, *, limit):
            calls.append((asset_id, limit))
            return (point,)

    result = operations_live.query_operations_latest_asset_measurements(
        _History(),
        "boiler-01",
        limit=32,
    )

    assert result == (point,)
    assert calls == [("boiler-01", 32)]


def test_multi_signal_trend_wrapper_uses_one_aggregation_query() -> None:
    expected = MultiSignalMeasurementHistoryAggregation(
        start_at=NOW - timedelta(hours=1),
        end_at=NOW,
        bucket_seconds=30.0,
        snapshot_id=7,
        buckets=(),
    )
    calls: list[tuple[str, tuple[str, ...], datetime, datetime, int]] = []

    class _History:
        def query_multi_signal_measurement_aggregation(
            self,
            asset_id,
            *,
            channel_ids,
            start_at,
            end_at,
            bucket_count,
        ):
            calls.append((asset_id, tuple(channel_ids), start_at, end_at, bucket_count))
            return expected

    result = operations_live.query_operations_multi_signal_measurement_aggregation(
        _History(),
        "boiler-01",
        channel_ids=("current-r", "temperature"),
        start_at=NOW - timedelta(hours=1),
        end_at=NOW,
        bucket_count=120,
    )

    assert result == expected
    assert calls == [
        (
            "boiler-01",
            ("current-r", "temperature"),
            NOW - timedelta(hours=1),
            NOW,
            120,
        )
    ]

