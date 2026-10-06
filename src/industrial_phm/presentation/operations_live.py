"""Presentation helpers for the Operations live-signal surface."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from html import escape
from math import isfinite
from numbers import Real

from industrial_phm.application.asset_history import MeasurementSourceQuality
from industrial_phm.application.measurement_history import MeasurementHistoryPage
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_live import LiveObservationSeries, LiveObservationView
from industrial_phm.presentation.measurement_history import latest_measurement_rows


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


def render_live_observation_html(
    view: LiveObservationView,
    *,
    silence_limit_seconds: float,
) -> str:
    """Render source-flow and selected-channel facts without inventing condition state."""
    if not isinstance(view, LiveObservationView):
        raise ValueError("view must be a LiveObservationView")
    _validate_silence_limit(silence_limit_seconds)
    if not view.series:
        return (
            '<section class="phm-shell">'
            '<div class="phm-section-title">Current observation</div>'
            '<div class="phm-card-detail">'
            "No mapped OPC UA live source is available for this signal."
            "</div></section>"
        )
    cards = "".join(
        _render_series(
            series,
            sampled_at=view.sampled_at,
            silence_limit_seconds=float(silence_limit_seconds),
        )
        for series in view.series
    )
    return (
        '<section class="phm-shell">'
        '<div class="phm-live-heading">'
        "<div>"
        '<div class="phm-section-title">Current observation</div>'
        f'<div class="phm-live-channel">{escape(view.channel_id)}</div>'
        "</div>"
        f'<div class="phm-card-detail">Sampled {_time_label(view.sampled_at)}</div>'
        "</div>"
        f'<div class="phm-live-grid">{cards}</div>'
        "</section>"
    )


def live_observation_css() -> str:
    return """
<style>
.phm-live-heading {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 1rem;
  margin-bottom: .8rem;
}
.phm-live-channel {
  font-size: 1.05rem;
  font-weight: 650;
}
.phm-live-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: .75rem;
}
.phm-live-card {
  background: var(--phm-surface);
  border: 1px solid var(--phm-border);
  border-radius: 10px;
  padding: 1rem;
}
.phm-live-source {
  color: var(--phm-muted);
  font-size: .82rem;
}
.phm-live-state-row {
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
  margin: .45rem 0 .55rem 0;
}
.phm-live-state {
  border: 1px solid var(--phm-border);
  border-radius: 999px;
  padding: .18rem .48rem;
  font-size: .78rem;
}
.phm-live-state-running { color: var(--phm-running); }
.phm-live-state-attention { color: var(--phm-attention); }
.phm-live-state-error { color: var(--phm-error); }
.phm-live-state-muted { color: var(--phm-muted); }
.phm-live-value {
  font-size: 2.15rem;
  font-weight: 700;
  line-height: 1.05;
  margin: .3rem 0 .8rem 0;
  font-variant-numeric: tabular-nums;
}
.phm-live-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .55rem .9rem;
}
.phm-live-fact-label {
  color: var(--phm-muted);
  font-size: .78rem;
}
.phm-live-fact-value {
  font-size: .88rem;
  overflow-wrap: anywhere;
}
.phm-live-details {
  margin-top: .8rem;
  border-top: 1px solid var(--phm-border);
  padding-top: .65rem;
  color: var(--phm-muted);
}
.phm-live-details summary {
  cursor: pointer;
  font-size: .78rem;
  user-select: none;
}
.phm-live-details .phm-live-facts {
  margin-top: .7rem;
}
@media (max-width: 720px) {
  .phm-live-heading { align-items: start; flex-direction: column; }
  .phm-live-facts { grid-template-columns: 1fr; }
}
</style>
"""


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


def _render_series(
    series: LiveObservationSeries,
    *,
    sampled_at: datetime,
    silence_limit_seconds: float,
) -> str:
    latest = series.latest_point
    row = None if latest is None else latest_measurement_rows((latest,), as_of=sampled_at)[0]
    value = "—" if row is None or row["value"] is None else _format_value(row["value"])
    unit = "" if row is None or row["unit"] == "unknown" else f" {row['unit']}"
    quality = "No stored observation" if row is None else str(row["source_quality"])
    if row is not None and row["quality"] != "no recorded issue":
        quality = f"{quality} · {row['quality']}"

    source_flow = live_source_flow_label(
        series,
        sampled_at=sampled_at,
        silence_limit_seconds=silence_limit_seconds,
    )
    quality_label, quality_class = _quality_badge(series)
    return (
        '<div class="phm-live-card">'
        f'<div class="phm-live-source">{escape(series.source_name)}</div>'
        '<div class="phm-live-state-row">'
        + _state_badge(
            f"Source flow · {source_flow}",
            _source_flow_class(source_flow),
        )
        + _state_badge(quality_label, quality_class)
        + "</div>"
        f'<div class="phm-live-value">{escape(value + unit)}</div>'
        '<div class="phm-live-facts">'
        + _fact(
            "Last source receipt",
            _relative_time(series.last_received_at, sampled_at=sampled_at),
        )
        + _fact(
            "Channel event time",
            _time_label(None if latest is None else latest.measurement.event_at),
        )
        + "</div>"
        '<details class="phm-live-details"><summary>Source details</summary>'
        '<div class="phm-live-facts">'
        + _fact("Session", _session_label(series.session_state))
        + _fact("Latest source timestamp", _time_label(series.last_source_timestamp))
        + _fact("Channel event lag", channel_event_lag_label(series))
        + _fact("Source quality", quality)
        + _fact("Source event rate", _rate_label(series.average_event_rate_hz))
        + "</div></details></div>"
    )


def _state_badge(label: str, css_class: str) -> str:
    return f'<span class="phm-live-state {escape(css_class)}">{escape(label)}</span>'


def _source_flow_class(label: str) -> str:
    if label == "Receiving":
        return "phm-live-state-running"
    if label in {"Reconnecting", "No recent source data", "Receive clock ahead"}:
        return "phm-live-state-attention"
    if label in {"Disconnected", "Stopped"}:
        return "phm-live-state-error"
    return "phm-live-state-muted"


def _quality_badge(series: LiveObservationSeries) -> tuple[str, str]:
    latest = series.latest_point
    if latest is None:
        return "Channel · no stored observation", "phm-live-state-muted"
    if latest.measurement.source_quality == MeasurementSourceQuality.NON_GOOD:
        return "Channel quality · non-good", "phm-live-state-error"
    if latest.measurement.source_quality == MeasurementSourceQuality.GOOD:
        return "Channel quality · good", "phm-live-state-running"
    return "Channel quality · unknown", "phm-live-state-muted"


def _fact(label: str, value: str) -> str:
    return (
        "<div>"
        f'<div class="phm-live-fact-label">{escape(label)}</div>'
        f'<div class="phm-live-fact-value">{escape(value)}</div>'
        "</div>"
    )


def _session_label(state: OpcUaPersistentSessionState | None) -> str:
    if state is None:
        return "Unavailable"
    return {
        OpcUaPersistentSessionState.CONNECTED: "Connected",
        OpcUaPersistentSessionState.CONNECTING: "Connecting",
        OpcUaPersistentSessionState.RECONNECT_WAIT: "Reconnecting",
        OpcUaPersistentSessionState.DISCONNECTED: "Disconnected",
        OpcUaPersistentSessionState.STOPPED: "Stopped",
    }[state]


def _relative_time(value: datetime | None, *, sampled_at: datetime) -> str:
    if value is None:
        return "No receipt recorded"
    age = (sampled_at - value).total_seconds()
    if age < 0:
        return f"{abs(age):.1f}s in future"
    if age < 60:
        return f"{age:.1f}s ago"
    if age < 3600:
        return f"{age / 60:.1f}m ago"
    return f"{age / 3600:.1f}h ago"


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.isoformat()


def _rate_label(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.3f} Hz"


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


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
