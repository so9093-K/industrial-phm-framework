"""Source-flow and channel-timing evidence helpers (UI-framework neutral)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from math import isfinite
from numbers import Real

from industrial_phm.application.measurement_history import MeasurementHistoryPage
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_live import LiveObservationSeries, LiveObservationView


def initial_signal_channel(
    channel_ids: Sequence[str],
    *,
    confirmed_channel_ids: Collection[str],
    selected: str | None,
) -> str:
    """Keep the user's explicit choice; otherwise open on a signal with confirmed meaning.

    Alphabetical order alone opened AI-Hub assets on an unresolved power channel.
    """
    if not channel_ids:
        raise ValueError("channel_ids must not be empty")
    if selected is not None and selected in channel_ids:
        return selected
    return next(
        (channel for channel in channel_ids if channel in confirmed_channel_ids),
        channel_ids[0],
    )


def live_observation_recent_page(view: LiveObservationView) -> MeasurementHistoryPage:
    """Flatten live-series points for the existing no-interpolation trend presenter."""
    if not isinstance(view, LiveObservationView):
        raise ValueError("view must be a LiveObservationView")
    points = tuple(
        sorted(
            (point for series in view.series for point in series.recent_points),
            key=lambda point: (
                point.measurement.event_at is None,
                (
                    0.0
                    if point.measurement.event_at is None
                    else point.measurement.event_at.timestamp()
                ),
                point.measurement.raw_evidence_id,
            ),
        )
    )
    return MeasurementHistoryPage(
        points=points,
        truncated=view.truncated,
        point_budget=view.point_budget,
    )


def live_source_flow_label(
    series: LiveObservationSeries,
    *,
    sampled_at: datetime,
    silence_limit_seconds: float,
) -> str:
    """Describe source-level receive evidence; never claim channel delivery from it."""
    if not isinstance(series, LiveObservationSeries):
        raise ValueError("series must be a LiveObservationSeries")
    if sampled_at.utcoffset() is None:
        raise ValueError("sampled_at must be timezone-aware")
    _validate_silence_limit(silence_limit_seconds)

    state = series.session_state
    if state is None:
        return "Unavailable"
    if state == OpcUaPersistentSessionState.CONNECTING:
        return "Connecting"
    if state == OpcUaPersistentSessionState.RECONNECT_WAIT:
        return "Reconnecting"
    if state == OpcUaPersistentSessionState.DISCONNECTED:
        return "Disconnected"
    if state == OpcUaPersistentSessionState.STOPPED:
        # A worker that ended on an error lost its session; it was not stopped on request.
        # The collection service restarts it with backoff (ADR-0010) only while it runs,
        # so "Disconnected" is the claim that holds either way.
        if (series.session_detail or "").startswith("worker-error"):
            return "Disconnected"
        return "Stopped"
    if series.last_received_at is None:
        return "Waiting for source data"
    age = (sampled_at - series.last_received_at).total_seconds()
    if age < -1:
        return "Receive clock ahead"
    if age > float(silence_limit_seconds):
        return "No recent source data"
    return "Receiving"


def channel_event_lag_label(series: LiveObservationSeries) -> str:
    """Compare selected-channel event time with latest source timestamp as a fact."""
    if not isinstance(series, LiveObservationSeries):
        raise ValueError("series must be a LiveObservationSeries")
    latest = series.latest_point
    if (
        latest is None
        or latest.measurement.event_at is None
        or series.last_source_timestamp is None
    ):
        return "Unavailable"
    lag = (series.last_source_timestamp - latest.measurement.event_at).total_seconds()
    if abs(lag) < 0.001:
        return "0s"
    if lag > 0:
        return f"{_duration_label(lag)} behind latest source timestamp"
    return f"{_duration_label(abs(lag))} ahead of latest source timestamp"


def _duration_label(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _validate_silence_limit(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError("silence_limit_seconds must be a finite number")
    if value <= 0:
        raise ValueError("silence_limit_seconds must be positive")


