"""Table rows and chart for three-phase unbalance evidence; no new interpretation."""

from __future__ import annotations

from datetime import UTC, datetime

from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.phase_unbalance import (
    ChannelSelection,
    PhaseUnbalanceAnalysis,
    UnbalanceSeriesResult,
)

_QUANTITY_LABEL = {"voltage": "전압 (상전압 기준)", "current": "전류"}


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def phase_unbalance_summary_rows(result: PhaseUnbalanceAnalysis) -> list[dict[str, object]]:
    return [
        {
            "quantity": _QUANTITY_LABEL[r.quantity.value],
            "evaluated_samples": r.evaluated_samples,
            "excluded_samples": sum(r.excluded_samples.values()),
            "median_percent": _round(r.median_percent),
            "p95_percent": _round(r.p95_percent),
            "max_percent": _round(r.max_percent),
            "max_at_utc": _utc(r.max_at),
            "channels": ", ".join(r.channels) or "none",
            "channel_selection": r.channel_selection.value,
            "note": _series_note(r),
            "carried_values": r.carried_values,
            "max_carry_age_seconds": r.max_carry_age_seconds,
        }
        for r in result.evidence.results
    ]


def _series_note(series: UnbalanceSeriesResult) -> str:
    """Why a series has no evaluated timestamps, when the counts alone cannot say."""
    if series.channel_selection == ChannelSelection.UNRESOLVED:
        return (
            "Not evaluated: no complete R/S/T channel set with this meaning was observed "
            "in the input (a phase is missing or unbound)."
        )
    if series.evaluated_samples == 0 and not series.excluded_samples:
        return "Not evaluated: the input has no timestamps for these channels."
    return ""


def phase_unbalance_provenance_rows(result: PhaseUnbalanceAnalysis) -> list[dict[str, object]]:
    evidence, run = result.evidence, result.run
    reference, config = evidence.input_reference, evidence.config
    if isinstance(reference, WindowInputReference):
        input_facts: list[tuple[str, object]] = [
            ("input", "finalized window accepted events (not a history re-query)"),
            ("window_id", reference.window_id),
            ("window_range_utc", f"{_utc(reference.window_start)} / {_utc(reference.window_end)}"),
            ("finalized_at_utc", _utc(reference.finalized_at)),
            ("accepted_events", reference.accepted_event_count),
            ("rejected_events", reference.rejected_event_count),
            ("missing_channels", ", ".join(reference.missing_channel_ids) or "none"),
            ("input_digest", f"{reference.digest_version}:{reference.input_digest}"),
        ]
    else:
        input_facts = [
            ("input", "Asset History at a fixed snapshot"),
            ("history_snapshot_id", reference.snapshot_id),
            ("requested_range_utc", f"{_utc(reference.start_at)} / {_utc(reference.end_at)}"),
            ("channels", ", ".join(reference.channel_ids)),
        ]
    facts: list[tuple[str, object]] = [
        ("analysis_run_id", run.analysis_run_id),
        ("evidence_id", evidence.evidence_id),
        ("capability", evidence.capability_id),
        ("algorithm_version", evidence.algorithm_version),
        ("source_id", evidence.source_id),
        *input_facts,
        ("evaluated_range_utc", f"{_utc(run.observed_start_at)} / {_utc(run.observed_end_at)}"),
        ("semantic_versions", ", ".join(evidence.semantic_versions) or "none"),
        ("alignment", _alignment_label(config.alignment.identity())),
        ("min_mean_voltage_v", config.min_mean_voltage_v),
        ("min_mean_current_a", config.min_mean_current_a),
        ("completed_at_utc", _utc(run.completed_at)),
        ("interpretation", evidence.interpretation),
    ]
    return [{"field": key, "value": str(value)} for key, value in facts]


def _alignment_label(identity: dict[str, object]) -> str:
    if identity["max_age_seconds"] is None:
        return str(identity["kind"])
    return f"{identity['kind']} max_age={identity['max_age_seconds']}s basis: {identity['basis']}"
