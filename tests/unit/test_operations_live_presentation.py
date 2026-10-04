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
    live_observation_css,
    live_observation_recent_page,
    render_live_observation_html,
)

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


def _point(*, seconds_ago: int, value: float) -> MeasurementHistoryPoint:
    return MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id=f"raw-{seconds_ago}",
            source_id="source-live",
            source_type=SourceType.OPCUA,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="current-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=NOW - timedelta(seconds=seconds_ago),
            value=value,
            status_good=True,
            ingestion_mode=HistoryIngestionMode.REPLAY,
        ),
        conflicting_duplicate=False,
    )


def _view() -> LiveObservationView:
    first = _point(seconds_ago=3, value=18.1)
    latest = _point(seconds_ago=2, value=18.2)
    return LiveObservationView(
        asset_id="boiler-01",
        channel_id="current-r",
        sampled_at=NOW,
        point_budget=120,
        truncated=False,
        series=(
            LiveObservationSeries(
                source_id="source-live",
                source_name="Boiler OPC UA",
                measurement_point_id="panel-main",
                status=OperationsMonitorStatus.RUNNING,
                session_state=OpcUaPersistentSessionState.CONNECTED,
                last_received_at=NOW - timedelta(milliseconds=400),
                last_source_timestamp=latest.measurement.event_at,
                average_event_rate_hz=6.0,
                latest_point=latest,
                recent_points=(first, latest),
            ),
        ),
    )


def test_live_observation_presents_current_value_receive_clock_and_event_time() -> None:
    rendered = render_live_observation_html(_view())

    assert "18.2" in rendered
    assert "Connected" in rendered
    assert "0.4s ago" in rendered
    assert "Source quality" in rendered
    assert "good" in rendered
    assert "2026-10-04T08:59:58+00:00" in rendered
    assert "6.000 Hz" in rendered
    assert "Healthy" not in rendered
    assert "Fault" not in rendered


def test_live_observation_recent_page_preserves_points_without_interpolation() -> None:
    page = live_observation_recent_page(_view())

    assert tuple(point.measurement.value for point in page.points) == (18.1, 18.2)
    assert page.point_budget == 120
    assert page.truncated is False


def test_live_observation_empty_state_does_not_claim_connection() -> None:
    view = LiveObservationView(
        asset_id="boiler-01",
        channel_id="current-r",
        sampled_at=NOW,
        point_budget=120,
        truncated=False,
        series=(),
    )

    rendered = render_live_observation_html(view)

    assert "No mapped OPC UA live source" in rendered
    assert "Connected" not in rendered


def test_live_observation_css_uses_operations_tokens() -> None:
    css = live_observation_css()

    assert "var(--phm-surface)" in css
    assert "var(--phm-border)" in css
    assert "var(--phm-muted)" in css
