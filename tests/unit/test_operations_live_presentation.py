from datetime import UTC, datetime, timedelta

from industrial_phm.application.asset_history import (
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
)
from industrial_phm.application.measurement_history import MeasurementHistoryPoint
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_live import LiveObservationSeries, LiveObservationView
from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.source_registration import SourceType
from industrial_phm.presentation.operations_live import (
    live_observation_recent_page,
    render_live_observation_html,
)

NOW = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)
EVENT_AT = datetime(2021, 7, 1, 1, 2, 3, tzinfo=UTC)


def _point() -> MeasurementHistoryPoint:
    return MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id="raw-live",
            source_id="live-opcua",
            source_type=SourceType.OPCUA,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="current-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=EVENT_AT,
            value=18.2,
            status_good=True,
            ingestion_mode=HistoryIngestionMode.REPLAY,
        ),
        conflicting_duplicate=False,
    )


def _view() -> LiveObservationView:
    point = _point()
    return LiveObservationView(
        asset_id="boiler-01",
        channel_id="current-r",
        sampled_at=NOW,
        point_budget=600,
        truncated=False,
        series=(
            LiveObservationSeries(
                source_id="live-opcua",
                source_name="Replay OPC UA",
                measurement_point_id="panel-main",
                status=OperationsMonitorStatus.RUNNING,
                session_state=OpcUaPersistentSessionState.CONNECTED,
                last_received_at=NOW - timedelta(seconds=1),
                last_source_timestamp=EVENT_AT,
                average_event_rate_hz=1.0,
                latest_point=point,
                recent_points=(point,),
            ),
        ),
    )


def test_live_presenter_separates_receive_age_from_recorded_event_time() -> None:
    rendered = render_live_observation_html(_view())

    assert "18.2" in rendered
    assert "Connected" in rendered
    assert "1.0s ago" in rendered
    assert EVENT_AT.isoformat() in rendered
    assert "good" in rendered
    assert "Healthy" not in rendered


def test_live_recent_page_preserves_raw_point_without_interpolation() -> None:
    view = _view()
    page = live_observation_recent_page(view)

    assert page.points == (view.series[0].latest_point,)
    assert page.point_budget == 600
    assert page.truncated is False
