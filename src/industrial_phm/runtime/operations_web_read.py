"""Versioned, bounded browser-safe read projection of the Operations evidence snapshot.

This is a read-only transport DTO. It never recomputes PHM results, opens repositories,
or treats a source/runtime status as asset health. UI-visible numeric evidence comes from
persisted capability-specific AnalysisRuns only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.asset_history import HistoricalInputReference
from industrial_phm.application.phase_unbalance import PhaseUnbalanceAnalysis
from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot

_API_VERSION = 1
_MAX_ITEMS = 100


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.utcoffset() is None:
        raise ValueError("API event time must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _bounded(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "items": items[:_MAX_ITEMS],
        "total": len(items),
        "truncated": len(items) > _MAX_ITEMS,
    }


def _input_reference(result: PhaseUnbalanceAnalysis) -> dict[str, object]:
    reference = result.evidence.input_reference
    if isinstance(reference, WindowInputReference):
        return {
            "kind": "finalized-window",
            "window_id": reference.window_id,
            "input_digest": reference.input_digest,
            "accepted_event_count": reference.accepted_event_count,
            "rejected_event_count": reference.rejected_event_count,
        }
    if isinstance(reference, HistoricalInputReference):
        return {
            "kind": "history-snapshot",
            "snapshot_id": reference.snapshot_id,
        }
    raise TypeError("unsupported phase analysis reference")


def _analysis(result: object) -> dict[str, object] | None:
    # Do not expose capability objects as unvalidated arbitrary JSON.
    if not isinstance(result, PhaseUnbalanceAnalysis):
        return None
    run = result.run
    evidence = result.evidence
    return {
        "analysis_run_id": run.analysis_run_id,
        "asset_id": run.asset_id,
        "source_id": run.source_id,
        "measurement_point_id": run.measurement_point_id,
        "capability_id": evidence.capability_id,
        "evidence_id": evidence.evidence_id,
        "algorithm_version": evidence.algorithm_version,
        "observed_start_at": _utc(run.observed_start_at),
        "observed_end_at": _utc(run.observed_end_at),
        "completed_at": _utc(run.completed_at),
        "data_quality": {
            "state": run.data_quality.state.value,
            "issue_codes": list(run.data_quality.issue_codes),
        },
        "input": _input_reference(result),
        "quantities": [
            {
                "quantity": series.quantity.value,
                "unit": "%",
                "evaluated_samples": series.evaluated_samples,
                "excluded_samples": dict(sorted(series.excluded_samples.items())),
                "median_percent": series.median_percent,
                "p95_percent": series.p95_percent,
                "max_percent": series.max_percent,
                "max_at": _utc(series.max_at),
                "channel_ids": list(series.channels),
                "channel_selection": series.channel_selection.value,
            }
            for series in evidence.results
        ],
        "interpretation": evidence.interpretation,
    }


def project_operations_monitor(snapshot: OperationsAppSnapshot) -> dict[str, object]:
    """Build an explicit GET /api/v1/monitor payload without filesystem or secrets.

    Collections have deterministic order and a fixed response cap. An unavailable or
    corrupt repository remains distinguishable from an empty but readable one through
    system_error_scopes; those scopes intentionally exclude exception details/paths.
    """
    assets: list[dict[str, object]] = [
        {
            "asset_id": asset.asset_id,
            "data_flow_status": asset.status.value,
            "source_count": asset.source_count,
            "last_data_at": _utc(asset.last_data_at),
            "latest_analysis_at": _utc(asset.latest_analysis_at),
            "pending_review_count": asset.pending_review_count,
            "attention_count": asset.attention_count,
        }
        for asset in snapshot.monitor.assets
    ]
    attention: list[dict[str, object]] = [
        {
            "attention_id": item.attention_id,
            "status": item.status.value,
            "destination": item.destination.value,
            "occurred_at": _utc(item.occurred_at),
            "asset_id": item.asset_id,
            "source_id": item.source_id,
            "measurement_point_id": item.measurement_point_id,
            "finding_id": item.finding_id,
        }
        for item in snapshot.monitor.attention
    ]
    phase_results: list[dict[str, object]] = []
    for item in sorted(
        snapshot.analysis_results,
        key=lambda value: (value.run.completed_at, value.run.analysis_run_id),
        reverse=True,
    ):
        result = _analysis(item)
        if result is not None:
            phase_results.append(result)
    skipped: list[dict[str, object]] = [
        {
            "asset_id": item.asset_id,
            "source_id": item.source_id,
            "measurement_point_id": item.measurement_point_id,
            "capability_id": item.capability_id,
            "state": item.state.value,
            "reason": item.reason,
            "window_id": item.window_id,
            "observed_start_at": _utc(item.observed_start_at),
            "observed_end_at": _utc(item.observed_end_at),
            "recorded_at": _utc(item.recorded_at),
        }
        for item in sorted(
            snapshot.skipped_analysis_attempts,
            key=lambda value: (value.recorded_at, value.window_id or ""),
            reverse=True,
        )
    ]
    reviews: list[dict[str, object]] = [
        {
            "finding_id": item.finding.finding_id,
            "asset_id": item.finding.asset_id,
            "analysis_run_id": item.finding.analysis_run_id,
            "status": item.status.value,
            "evidence_ids": list(item.finding.evidence_refs),
        }
        for item in snapshot.overview.review_summaries
    ]
    return {
        "schema_version": _API_VERSION,
        "assessed_at": _utc(snapshot.assessed_at),
        "meaning": "observations-and-review-evidence-not-asset-health",
        "assets": _bounded(assets),
        "attention": _bounded(attention),
        "phase_unbalance_analyses": _bounded(phase_results),
        "skipped_analysis_attempts": _bounded(skipped),
        "review_requests": _bounded(reviews),
        "system_error_scopes": sorted({item.scope for item in snapshot.system_errors}),
    }
