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
    channel_event_lag_label,
    initial_signal_channel,
    live_observation_recent_page,
    live_source_flow_label,
    render_live_observation_html,
)

NOW = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)
EVENT_AT = datetime(2021, 7, 1, 1, 2, 3, tzinfo=UTC)


def _point(
    *,
    event_at: datetime = EVENT_AT,
    status_good: bool = True,
) -> MeasurementHistoryPoint:
    return MeasurementHistoryPoint(
        HistoricalMeasurement(
            raw_evidence_id=f"raw-live-{event_at.timestamp()}-{status_good}",
            source_id="live-opcua",
            source_type=SourceType.OPCUA,
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_id="current-r",
            event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
            event_at=event_at,
            value=18.2,
            status_good=status_good,
            ingestion_mode=HistoryIngestionMode.REPLAY,
        ),
        conflicting_duplicate=False,
    )


def _series(
    *,
    session_state: OpcUaPersistentSessionState = OpcUaPersistentSessionState.CONNECTED,
    last_received_at: datetime | None = NOW - timedelta(seconds=1),
    last_source_timestamp: datetime | None = EVENT_AT,
    latest_point: MeasurementHistoryPoint | None = None,
) -> LiveObservationSeries:
    point = _point() if latest_point is None else latest_point
    return LiveObservationSeries(
        source_id="live-opcua",
        source_name="Replay OPC UA",
        measurement_point_id="panel-main",
        status=OperationsMonitorStatus.RUNNING,
        session_state=session_state,
        last_received_at=last_received_at,
        last_source_timestamp=last_source_timestamp,
        average_event_rate_hz=1.0,
        latest_point=point,
        recent_points=() if point is None else (point,),
    )


def _view(*, series: LiveObservationSeries | None = None) -> LiveObservationView:
    selected = _series() if series is None else series
    return LiveObservationView(
        asset_id="boiler-01",
        channel_id="current-r",
        sampled_at=NOW,
        point_budget=600,
        truncated=False,
        series=(selected,),
    )


def test_live_presenter_separates_source_flow_from_recorded_channel_time() -> None:
    rendered = render_live_observation_html(_view(), silence_limit_seconds=30.0)

    assert "Current observation" in rendered
    assert "18.2" in rendered
    assert "Source flow · Receiving" in rendered
    assert "Last source receipt" in rendered
    assert "1.0s ago" in rendered
    assert "Channel event time" in rendered
    assert EVENT_AT.isoformat() in rendered
    assert "Channel quality · good" in rendered
    assert "<details" in rendered
    assert "Source details" in rendered
    assert "Healthy" not in rendered


def test_live_source_flow_surfaces_reconnect_and_source_silence() -> None:
    reconnecting = _series(
        session_state=OpcUaPersistentSessionState.RECONNECT_WAIT,
        last_received_at=NOW - timedelta(seconds=5),
    )
    silent = _series(last_received_at=NOW - timedelta(seconds=31))

    assert (
        live_source_flow_label(
            reconnecting,
            sampled_at=NOW,
            silence_limit_seconds=30.0,
        )
        == "Reconnecting"
    )
    assert (
        live_source_flow_label(
            silent,
            sampled_at=NOW,
            silence_limit_seconds=30.0,
        )
        == "No recent source data"
    )


def test_live_presenter_marks_non_good_channel_quality_explicitly() -> None:
    series = _series(latest_point=_point(status_good=False))

    rendered = render_live_observation_html(
        _view(series=series),
        silence_limit_seconds=30.0,
    )

    assert "Channel quality · non-good" in rendered
    assert "non-good" in rendered


def test_channel_event_lag_is_factual_relative_to_latest_source_timestamp() -> None:
    channel_point = _point(event_at=EVENT_AT - timedelta(seconds=12))
    series = _series(
        latest_point=channel_point,
        last_source_timestamp=EVENT_AT,
    )

    assert channel_event_lag_label(series) == "12.0s behind latest source timestamp"


def test_live_presenter_keeps_missing_channel_observation_distinct_from_source_flow() -> None:
    series = _series(
        latest_point=None,
        last_source_timestamp=EVENT_AT,
    )
    series = LiveObservationSeries(
        source_id=series.source_id,
        source_name=series.source_name,
        measurement_point_id=series.measurement_point_id,
        status=series.status,
        session_state=series.session_state,
        last_received_at=series.last_received_at,
        last_source_timestamp=series.last_source_timestamp,
        average_event_rate_hz=series.average_event_rate_hz,
        latest_point=None,
        recent_points=(),
    )

    rendered = render_live_observation_html(
        _view(series=series),
        silence_limit_seconds=30.0,
    )

    assert "Source flow · Receiving" in rendered
    assert "Channel · no stored observation" in rendered
    assert "Channel event lag" in rendered
    assert "Unavailable" in rendered


def test_live_recent_page_preserves_raw_point_without_interpolation() -> None:
    view = _view()
    page = live_observation_recent_page(view)

    assert page.points == (view.series[0].latest_point,)
    assert page.point_budget == 600
    assert page.truncated is False


def test_signals_open_on_confirmed_meaning_and_keep_an_explicit_choice() -> None:
    channels = ("R상무효전력", "R상전류", "R상전압", "온도")
    confirmed = {"R상전류", "R상전압"}

    assert initial_signal_channel(channels, confirmed_channel_ids=confirmed, selected=None) == (
        "R상전류"
    )
    # An explicit choice survives a refresh, even for an unresolved channel.
    assert (
        initial_signal_channel(channels, confirmed_channel_ids=confirmed, selected="온도") == "온도"
    )
    # A choice from another asset that this asset lacks falls back to the default.
    assert (
        initial_signal_channel(channels, confirmed_channel_ids=confirmed, selected="T상전류")
        == "R상전류"
    )
    assert initial_signal_channel(("a", "b"), confirmed_channel_ids=set(), selected=None) == "a"
