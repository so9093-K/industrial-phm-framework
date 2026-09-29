"""Table rows and chart for three-phase unbalance evidence; no new interpretation."""

from __future__ import annotations

import importlib
import io
from datetime import UTC, datetime

from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.phase_unbalance import PhaseUnbalanceAnalysis

_QUANTITY_LABEL = {"voltage": "전압 (상전압 기준)", "current": "전류"}


def _utc(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def phase_unbalance_run_options(
    results: tuple[PhaseUnbalanceAnalysis, ...], asset_id: str
) -> dict[str, str]:
    """Newest first; label shows completion time, source and analysed range."""
    options = {}
    for result in sorted(results, key=lambda r: r.run.completed_at, reverse=True):
        if result.run.asset_id != asset_id:
            continue
        reference = result.evidence.input_reference
        label = (
            f"{_utc(result.run.completed_at)} · {result.run.source_id} · "
            f"{_utc(reference.start_at)} / {_utc(reference.end_at)}"
        )
        options[label] = result.run.analysis_run_id
    return options


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
        }
        for r in result.evidence.results
    ]


def phase_unbalance_exclusion_rows(result: PhaseUnbalanceAnalysis) -> list[dict[str, object]]:
    return [
        {"quantity": _QUANTITY_LABEL[r.quantity.value], "reason": reason, "timestamps": count}
        for r in result.evidence.results
        for reason, count in sorted(r.excluded_samples.items())
    ]


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
        ("min_mean_voltage_v", config.min_mean_voltage_v),
        ("min_mean_current_a", config.min_mean_current_a),
        ("completed_at_utc", _utc(run.completed_at)),
        ("interpretation", evidence.interpretation),
    ]
    return [{"field": key, "value": str(value)} for key, value in facts]


def render_phase_unbalance_svg(result: PhaseUnbalanceAnalysis) -> str:
    """Per time bucket: median as points, max as a vertical extent; gaps stay empty."""
    figure_module = importlib.import_module("matplotlib.figure")
    figure = figure_module.Figure(figsize=(11, 4.6), layout="constrained")
    reference = result.evidence.input_reference
    axes_list = figure.subplots(2, 1, sharex=True)
    titles = {"voltage": "Voltage unbalance (phase-voltage basis)", "current": "Current unbalance"}
    for axes, series in zip(axes_list, result.evidence.results, strict=True):
        times = [b.start_at + (b.end_at - b.start_at) / 2 for b in series.buckets]
        if series.buckets:
            axes.vlines(
                times,
                [b.median_percent for b in series.buckets],
                [b.max_percent for b in series.buckets],
                color="C0",
                alpha=0.35,
                label="bucket max",
            )
            axes.scatter(
                times, [b.median_percent for b in series.buckets], s=10, color="C0", label="median"
            )
            axes.legend(fontsize="small", loc="upper right")
        else:
            axes.text(0.5, 0.5, "no eligible samples", transform=axes.transAxes, ha="center")
        axes.set_title(
            f"{titles[series.quantity.value]} · n={series.evaluated_samples}", fontsize=10
        )
        axes.set_ylabel("%")
        axes.grid(alpha=0.2)
    axes_list[-1].set_xlim(reference.start_at.astimezone(UTC), reference.end_at.astimezone(UTC))
    axes_list[-1].set_xlabel("Requested event-time range (UTC)")
    figure.autofmt_xdate()
    output = io.StringIO()
    figure.savefig(output, format="svg")
    return output.getvalue()
