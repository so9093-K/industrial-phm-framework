"""Versioned, bounded browser-safe read projection of the Operations evidence snapshot.

This is a read-only transport DTO. It never recomputes PHM results, opens repositories,
or treats a source/runtime status as asset health. UI-visible numeric evidence comes from
persisted capability-specific AnalysisRuns only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from industrial_phm.application import FileSourceConfig
from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.asset_display import resolve_asset_display_names
from industrial_phm.application.asset_history import HistoricalInputReference
from industrial_phm.application.file_feature_analysis import RegisteredFileFeatureAnalysis
from industrial_phm.application.phase_unbalance import PhaseUnbalanceAnalysis
from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot
from industrial_phm.runtime.operations_status import OperationsRuntimeStatus

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


def _file_analysis(result: RegisteredFileFeatureAnalysis) -> dict[str, object]:
    """Expose persisted CSV features without inventing physical units or diagnoses."""
    run = result.run
    evidence = result.evidence
    return {
        "analysis_run_id": run.analysis_run_id,
        "asset_id": run.asset_id,
        "source_id": run.source_id,
        "measurement_point_id": run.measurement_point_id,
        "capability_id": evidence.capability_id,
        "evidence_id": evidence.evidence_id,
        "feature_set_id": evidence.feature_set_id,
        "observed_start_at": _utc(run.observed_start_at),
        "observed_end_at": _utc(run.observed_end_at),
        "completed_at": _utc(run.completed_at),
        "data_quality": {
            "state": run.data_quality.state.value,
            "issue_codes": list(run.data_quality.issue_codes),
        },
        "source_snapshot_sha256": evidence.source_snapshot_sha256,
        "features": [
            {"name": name, "value": value}
            for name, value in zip(evidence.feature_names, evidence.values, strict=True)
        ],
        "interpretation": (
            "descriptive CSV statistical features; measurement units and vibration "
            "semantics are not confirmed; not a fault, alarm or health assessment"
        ),
    }


def project_operations_monitor(
    snapshot: OperationsAppSnapshot, *, phm: dict[str, Any] | None = None
) -> dict[str, object]:
    """Build an explicit GET /api/v1/monitor payload without filesystem or secrets.

    Collections have deterministic order and a fixed response cap. An unavailable or
    corrupt repository remains distinguishable from an empty but readable one through
    system_error_scopes; those scopes intentionally exclude exception details/paths.
    """
    # The newest stored event time is a measurement time; last_data_at stays the newest
    # receipt (a file read or a live arrival), which is a different clock.
    stored_until = {item.asset_id: item.end_at for item in snapshot.history_assets}
    file_only = {
        asset_id
        for asset_id in {source.asset_id for source in snapshot.registered_sources}
        if all(
            isinstance(source.config, FileSourceConfig)
            for source in snapshot.registered_sources
            if source.asset_id == asset_id
        )
    }

    def flow(asset_id: str, status: str) -> str:
        # A file has no receive cadence to judge, and pausing it stops nothing that would
        # arrive; its stored rows are the whole record. File read errors stay visible.
        if (
            status in {"unavailable", "stopped"}
            and asset_id in file_only
            and asset_id in stored_until
        ):
            return "stored-history"
        return status

    assets: list[dict[str, object]] = [
        {
            "asset_id": asset.asset_id,
            "data_flow_status": flow(asset.asset_id, asset.status.value),
            "source_count": asset.source_count,
            "last_data_at": _utc(asset.last_data_at),
            "last_observed_at": _utc(stored_until.get(asset.asset_id)),
            "latest_analysis_at": _utc(asset.latest_analysis_at),
            "pending_review_count": asset.pending_review_count,
            "attention_count": asset.attention_count,
        }
        for asset in snapshot.monitor.assets
    ]
    known_assets = {str(asset["asset_id"]) for asset in assets}
    for historical in snapshot.history_assets:
        if historical.asset_id in known_assets:
            continue
        # A persisted observation does not require a currently registered source.
        # Its event time is history, never proof of a live connection or receipt.
        assets.append(
            {
                "asset_id": historical.asset_id,
                "data_flow_status": "stored-history",
                "source_count": 0,
                "last_data_at": None,
                "last_observed_at": _utc(historical.end_at),
                "latest_analysis_at": None,
                "pending_review_count": 0,
                "attention_count": 0,
            }
        )
        known_assets.add(historical.asset_id)
    # Model bindings and delivered waveforms exist independently of registered FILE/
    # OPC UA sources and DuckLake history. Preserve those actual asset identities in
    # the common list, including streams no model reads. Delivery ordinals/times are
    # never invented as the original measurement's event time.
    if phm is not None:
        for item in [*phm["items"], *phm["unbound_streams"]]:
            asset_id = item["asset_id"]
            position = _delivered_position(item)
            if asset_id in known_assets:
                row = next(row for row in assets if row["asset_id"] == asset_id)
                last = row.get("last_position")
                if position is not None and (not isinstance(last, int) or position > last):
                    row["last_position"] = position
                continue
            assets.append(
                {
                    "asset_id": asset_id,
                    "data_flow_status": "stored-history"
                    if item.get("latest_delivered") or item.get("last_ordinal")
                    else "waiting",
                    "source_count": 0,
                    "last_data_at": None,
                    "last_observed_at": None,
                    "latest_analysis_at": None,
                    "pending_review_count": None,
                    "attention_count": None,
                    # The delivery order of the newest waveform; it has no measurement clock.
                    "last_position": position,
                }
            )
            known_assets.add(asset_id)
    display_names = resolve_asset_display_names(snapshot.registered_sources)
    for asset_row in assets:
        asset_row["asset_display_name"] = display_names.name(str(asset_row["asset_id"]))
    assets.sort(key=lambda item: str(item["asset_id"]))
    asset_list = _bounded(assets)
    if phm is not None and phm["truncated"]:
        asset_list["truncated"] = True
    attention: list[dict[str, object]] = [
        {
            "attention_id": item.attention_id,
            "title": item.title,
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
    file_results: list[dict[str, object]] = []
    for item in sorted(
        snapshot.analysis_results,
        key=lambda value: (value.run.completed_at, value.run.analysis_run_id),
        reverse=True,
    ):
        result = _analysis(item)
        if result is not None:
            phase_results.append(result)
        elif isinstance(item, RegisteredFileFeatureAnalysis):
            file_results.append(_file_analysis(item))
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
        "assets": asset_list,
        "attention": _bounded(attention),
        "phase_unbalance_analyses": _bounded(phase_results),
        "file_feature_analyses": _bounded(file_results),
        "skipped_analysis_attempts": _bounded(skipped),
        "review_requests": _bounded(reviews),
        "system_error_scopes": sorted({item.scope for item in snapshot.system_errors}),
    }


def _delivered_position(item: dict[str, Any]) -> int | None:
    delivered = item.get("latest_delivered")
    position = delivered.get("position") if isinstance(delivered, dict) else None
    position = position if position is not None else item.get("last_ordinal")
    return position if isinstance(position, int) and not isinstance(position, bool) else None


def project_operations_runtime_status(status: OperationsRuntimeStatus) -> dict[str, object]:
    """Expose current local process evidence, not a physical equipment-health verdict.

    Process existence and heartbeat freshness are observation-time signals.
    Runtime failure details and filesystem/log paths stay outside the Web API.
    """
    supervisor = status.supervisor
    return {
        "schema_version": _API_VERSION,
        "assessed_at": _utc(status.assessed_at),
        "meaning": "local-process-readiness-not-collection-receipt-or-asset-health",
        "ready": status.ready,
        "supervisor": {
            "condition": supervisor.condition.value,
            "pid": supervisor.process.pid if supervisor.process is not None else None,
            "heartbeat_at": _utc(supervisor.heartbeat_at),
        },
        "components": [
            {
                "kind": component.kind.value,
                "condition": component.condition.value,
                "pid": component.process.pid if component.process is not None else None,
                "runtime_state": component.runtime_state,
                "heartbeat_at": _utc(component.heartbeat_at),
            }
            for component in status.components
        ],
    }
