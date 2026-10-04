"""Presentation helpers for the Operations live-signal surface."""

from __future__ import annotations

from datetime import datetime
from html import escape

from industrial_phm.application.measurement_history import MeasurementHistoryPage
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_live import LiveObservationSeries, LiveObservationView
from industrial_phm.presentation.measurement_history import latest_measurement_rows


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


def render_live_observation_html(view: LiveObservationView) -> str:
    """Render current observation facts without promoting them to an asset verdict."""
    if not isinstance(view, LiveObservationView):
        raise ValueError("view must be a LiveObservationView")
    if not view.series:
        return (
            '<section class="phm-shell">'
            '<div class="phm-section-title">Live observation</div>'
            '<div class="phm-card-detail">'
            "No mapped OPC UA live source is available for this signal."
            "</div></section>"
        )
    cards = "".join(_render_series(series, sampled_at=view.sampled_at) for series in view.series)
    return (
        '<section class="phm-shell">'
        '<div class="phm-live-heading">'
        "<div>"
        '<div class="phm-section-title">Live observation</div>'
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
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
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
.phm-live-value {
  font-size: 1.8rem;
  font-weight: 650;
  margin: .35rem 0 .55rem 0;
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
@media (max-width: 720px) {
  .phm-live-heading { align-items: start; flex-direction: column; }
  .phm-live-facts { grid-template-columns: 1fr; }
}
</style>
"""


def _render_series(series: LiveObservationSeries, *, sampled_at: datetime) -> str:
    latest = series.latest_point
    row = None if latest is None else latest_measurement_rows((latest,), as_of=sampled_at)[0]
    value = "—" if row is None or row["value"] is None else _format_value(row["value"])
    unit = "" if row is None or row["unit"] == "unknown" else f" {row['unit']}"
    quality = "No stored observation" if row is None else str(row["source_quality"])
    if row is not None and row["quality"] != "no recorded issue":
        quality = f"{quality} · {row['quality']}"
    return (
        '<div class="phm-live-card">'
        f'<div class="phm-live-source">{escape(series.source_name)}</div>'
        f'<div class="phm-live-value">{escape(value + unit)}</div>'
        '<div class="phm-live-facts">'
        + _fact("Session", _session_label(series.session_state))
        + _fact("Last received", _relative_time(series.last_received_at, sampled_at=sampled_at))
        + _fact("Event time", _time_label(None if latest is None else latest.measurement.event_at))
        + _fact("Source timestamp", _time_label(series.last_source_timestamp))
        + _fact("Source quality", quality)
        + _fact("Event rate", _rate_label(series.average_event_rate_hz))
        + "</div></div>"
    )


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


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
