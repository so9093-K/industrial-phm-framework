"""Pure Operations presenters without marimo or UI-framework dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from industrial_phm.application.asset_detail import (
    AssetDetail,
    AssetEvidenceEvent,
    AssetEvidenceTimeline,
)
from industrial_phm.application.observation import (
    AssetObservationSummary,
    SourceSnapshotEvidence,
)
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.operations_attention import (
    AttentionItem,
    OperationsAttentionQueue,
)
from industrial_phm.application.operations_overview import OperationsOverview
from industrial_phm.application.source_health import SourceDataFlowState


def render_asset_analysis_markdown(detail: AssetDetail) -> str | None:
    """Render recorded AnalysisRun identity, capability and source provenance."""
    if not isinstance(detail, AssetDetail):
        raise ValueError("detail must be an AssetDetail")
    if not detail.analysis_runs:
        return None

    rows = "\n".join(
        (
            f"| {_format_code(run.analysis_run_id)} | "
            f"{_format_code(run.source_id)} | "
            f"{_format_code(run.measurement_point_id or 'Not recorded')} | "
            f"{run.observed_start_at.isoformat()} → {run.observed_end_at.isoformat()} | "
            f"{run.completed_at.isoformat()} | "
            f"{_format_code_list(run.capability_ids)} | "
            f"{_format_snapshot_list(run.source_snapshots)} |"
        )
        for run in detail.analysis_runs
    )
    return (
        "### Analysis evidence\n\n"
        "AnalysisRun과 capability/source provenance를 그대로 표시하며 condition verdict를 "
        "추가하지 않습니다.\n\n"
        "| Analysis run | Source | Measurement point | Observed window | Completed | "
        "Capabilities | Source snapshots |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n" + rows
    )


def render_asset_findings_markdown(detail: AssetDetail) -> str | None:
    """Render versioned finding semantics and evidence references for one asset."""
    if not isinstance(detail, AssetDetail):
        raise ValueError("detail must be an AssetDetail")
    if not detail.findings:
        return None

    rows = "\n".join(
        (
            f"| {finding.observed_at.isoformat()} | "
            f"{_format_code(finding.finding_id)} | "
            f"{_format_code(finding.analysis_run_id)} | "
            f"{_format_code(finding.state)} | "
            f"{_format_code(finding.finding_semantics_id)} | "
            f"{_format_code_list(finding.evidence_refs)} |"
        )
        for finding in detail.findings
    )
    return (
        "### Finding evidence\n\n"
        "State의 의미는 finding_semantics_id가 소유하며 이 표는 fault/health verdict를 "
        "추론하지 않습니다.\n\n"
        "| Observed | Finding | Analysis run | State | Semantics | Evidence refs |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + rows
    )


def render_asset_sources_markdown(detail: AssetDetail) -> str | None:
    """Render current source mappings and data-flow facts for one asset."""
    if not isinstance(detail, AssetDetail):
        raise ValueError("detail must be an AssetDetail")
    if not detail.source_contexts:
        return None

    rows = "\n".join(
        (
            f"| {_format_code(context.source.source_id)} | "
            f"{context.source.source_type.value} | "
            f"{_format_code(context.source.measurement_point_id or 'Not recorded')} | "
            f"{context.health.lifecycle.state.value} | "
            f"{context.health.data_flow_state.name} | "
            f"{_format_optional_time(context.health.latest_observed_at)} | "
            f"{_format_optional_time(context.health.latest_received_at)} |"
        )
        for context in detail.source_contexts
    )
    return (
        "### Sources\n\n"
        "Lifecycle/data-flow는 source evidence이며 asset condition verdict가 아닙니다.\n\n"
        "| Source | Type | Measurement point | Lifecycle | Data flow | "
        "Observed | Received |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n" + rows
    )


def render_asset_timeline_markdown(
    timeline: AssetEvidenceTimeline,
) -> str | None:
    """Render timezone-aware comparable evidence events in chronological order."""
    if not isinstance(timeline, AssetEvidenceTimeline):
        raise ValueError("timeline must be an AssetEvidenceTimeline")
    if not timeline.events:
        return None
    rows = "\n".join(_render_timeline_row(item) for item in timeline.events)
    return (
        "### Evidence Timeline\n\n"
        "서로 다른 clock 의미는 Time basis로 분리하고 timezone-aware 시각만 "
        "chronological ordering에 사용합니다.\n\n"
        "| Event time | Time basis | Event | Scope | Evidence |\n"
        "| --- | --- | --- | --- | --- |\n" + rows
    )


def render_unplaced_asset_evidence_markdown(
    timeline: AssetEvidenceTimeline,
) -> str | None:
    """Render evidence whose missing/naive time cannot join the chronology."""
    if not isinstance(timeline, AssetEvidenceTimeline):
        raise ValueError("timeline must be an AssetEvidenceTimeline")
    if not timeline.unplaced_events:
        return None
    rows = "\n".join(
        (
            f"| {item.time_basis.value} | {item.kind.value} | "
            f"{_format_timeline_scope(item)} | {_format_timeline_evidence(item)} |"
        )
        for item in timeline.unplaced_events
    )
    return (
        "### Time not comparable\n\n"
        "Missing 또는 timezone-naive evidence time은 다른 clock과 임의로 정렬하지 않습니다.\n\n"
        "| Time basis | Event | Scope | Evidence |\n"
        "| --- | --- | --- | --- |\n" + rows
    )


def render_attention_queue_markdown(
    queue: OperationsAttentionQueue,
) -> str | None:
    """Render factual attention rows, or None when the current queue is empty."""
    if not isinstance(queue, OperationsAttentionQueue):
        raise ValueError("queue must be an OperationsAttentionQueue")
    if not queue.items:
        return None

    rows = tuple(_render_attention_row(item) for item in queue.items)
    return (
        "### Attention Queue\n\n"
        "Risk/severity 점수 없이 현재 evidence와 human workflow 상태만 정렬합니다. "
        "OPEN review는 UNHANDLED, 그 외 unresolved fact는 ACTIVE입니다. "
        "Data Quality item은 현재 로드된 observation evidence 범위입니다.\n\n"
        "| Handling | Category | Evidence time | Asset | Scope | Evidence |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows)
    )


def render_source_data_flow_markdown(overview: OperationsOverview) -> str:
    """Render source data-flow counts without promoting them to asset health."""
    if not isinstance(overview, OperationsOverview):
        raise ValueError("overview must be an OperationsOverview")

    states = (
        SourceDataFlowState.SOURCE_ERROR,
        SourceDataFlowState.NO_RECEIPT,
        SourceDataFlowState.STALE,
        SourceDataFlowState.FRESH,
        SourceDataFlowState.TIMING_UNAVAILABLE,
        SourceDataFlowState.FRESHNESS_NOT_CONFIGURED,
        SourceDataFlowState.INACTIVE,
    )
    rows = "\n".join(
        f"| {state.name} | {overview.source_data_flow_count(state)} |" for state in states
    )
    return (
        "### Source data flow\n\n"
        "Source lifecycle/receipt/freshness evidence를 같은 read model에서 집계합니다. "
        "이 상태는 asset health가 아닙니다.\n\n"
        "| State | Sources |\n"
        "| --- | ---: |\n" + rows
    )


def render_analysis_quality_markdown(run: AnalysisRun) -> str:
    """Render AnalysisRun input quality and recorded source snapshot provenance."""
    if not isinstance(run, AnalysisRun):
        raise ValueError("run must be an AnalysisRun")

    if run.data_quality.issues:
        issue_rows = "\n".join(
            (
                f"| {issue.severity.value} | {_format_code(issue.code)} | "
                f"{_escape_table_cell(issue.message)} |"
            )
            for issue in run.data_quality.issues
        )
        issues = "| Severity | Code | Evidence |\n| --- | --- | --- |\n" + issue_rows
    else:
        issues = "No recorded data-quality issue under this analysis input validation."

    return (
        "### Analysis input quality & provenance\n\n"
        f"Recorded data-quality state: **{run.data_quality.state.value.upper()}**. "
        "This state describes input validation evidence, not asset health.\n\n"
        f"{issues}\n\n"
        "| Provenance | Recorded value |\n"
        "| --- | --- |\n"
        f"| Source snapshots | {_format_snapshot_list(run.source_snapshots)} |"
    )


def render_observation_provenance_markdown(
    observation: AssetObservationSummary,
) -> str:
    """Render source snapshot and declared validation-policy evidence."""
    if not isinstance(observation, AssetObservationSummary):
        raise ValueError("observation must be an AssetObservationSummary")

    snapshot = (
        "Not recorded"
        if observation.source_snapshot is None
        else (
            f"{_format_code(observation.source_snapshot.name)} · "
            f"{_format_code(observation.source_snapshot.sha256)} · "
            f"{observation.source_snapshot.size_bytes:,} bytes"
        )
    )
    if observation.validation_policy is None:
        timestamp_field = "Not recorded"
        minimum_samples = "Not recorded"
        tolerance = "Not recorded"
    else:
        timestamp_field = _format_code(
            observation.validation_policy.source_timestamp_field or "Not declared"
        )
        minimum_samples = f"{observation.validation_policy.minimum_sample_count:,}"
        tolerance_value = observation.validation_policy.sampling_rate_tolerance_ratio
        tolerance = "Not declared" if tolerance_value is None else f"{tolerance_value:g}"

    return (
        "### Source provenance & validation\n\n"
        "| Evidence | Recorded value |\n"
        "| --- | --- |\n"
        f"| Source snapshot | {snapshot} |\n"
        f"| Source timestamp field | {timestamp_field} |\n"
        f"| Minimum samples | {minimum_samples} |\n"
        f"| Sampling-rate tolerance ratio | {tolerance} |"
    )


def render_observation_markdown(observation: AssetObservationSummary) -> str:
    """Render recorded observation identity and availability facts."""
    if not isinstance(observation, AssetObservationSummary):
        raise ValueError("observation must be an AssetObservationSummary")

    start = _format_optional_time(observation.observed_start_at)
    end = _format_optional_time(observation.observed_end_at)
    point = observation.measurement_point_id or "Not recorded"
    sampling_rate = (
        "Not declared"
        if observation.sampling_rate_hz is None
        else f"{observation.sampling_rate_hz:g} Hz"
    )
    channels = ", ".join(_escape_table_cell(item) for item in observation.channels)
    return (
        "### Observation\n\n"
        "| Field | Value |\n"
        "| --- | --- |\n"
        f"| Asset | {_format_code(observation.asset_id)} |\n"
        f"| Measurement point | {_format_code(point)} |\n"
        f"| Source | {_format_code(observation.source_id)} |\n"
        f"| Observed start | {start} |\n"
        f"| Observed end | {end} |\n"
        f"| Samples | {observation.sample_count:,} |\n"
        f"| Channels | {channels} |\n"
        f"| Sampling rate | {sampling_rate} |"
    )


def render_data_quality_issues_markdown(
    observation: AssetObservationSummary,
) -> str | None:
    """Render recorded quality issues, or None when no issue is recorded."""
    if not isinstance(observation, AssetObservationSummary):
        raise ValueError("observation must be an AssetObservationSummary")
    if not observation.data_quality.issues:
        return None

    rows = "\n".join(
        (
            f"| {issue.severity.value} | {_format_code(issue.code)} | "
            f"{_escape_table_cell(issue.message)} |"
        )
        for issue in observation.data_quality.issues
    )
    return "| Severity | Code | Evidence |\n| --- | --- | --- |\n" + rows


def _render_timeline_row(item: AssetEvidenceEvent) -> str:
    event_at = item.comparable_at
    if event_at is None:
        raise ValueError("timeline row requires a comparable event time")
    return (
        f"| {event_at.isoformat()} | {item.time_basis.value} | {item.kind.value} | "
        f"{_format_timeline_scope(item)} | {_format_timeline_evidence(item)} |"
    )


def _format_timeline_scope(item: AssetEvidenceEvent) -> str:
    value = item.source_id or item.analysis_run_id or item.finding_id or "—"
    return _format_code(value)


def _format_timeline_evidence(item: AssetEvidenceEvent) -> str:
    values: list[str] = []
    if item.lifecycle_state is not None:
        values.append(f"lifecycle {_format_code(item.lifecycle_state.value)}")
    if item.analysis_run_id is not None:
        values.append(f"analysis {_format_code(item.analysis_run_id)}")
    if item.capability_id is not None:
        values.append(f"capability {_format_code(item.capability_id)}")
    if item.finding_id is not None:
        values.append(f"finding {_format_code(item.finding_id)}")
    if item.review_action is not None:
        values.append(f"review {_format_code(item.review_action.value)}")
    if item.window_start_at is not None or item.window_end_at is not None:
        values.append(
            "window "
            f"{_format_optional_time(item.window_start_at)} → "
            f"{_format_optional_time(item.window_end_at)}"
        )
    if item.detail is not None:
        values.append(_escape_table_cell(item.detail))
    return " · ".join(values) if values else "Recorded evidence"


def _render_attention_row(item: AttentionItem) -> str:
    when = _format_optional_time(item.occurred_at)
    asset = "—" if item.asset_identity is None else _format_code(item.asset_identity.asset_id)
    scope = item.source_id or item.finding_id or item.system_scope or "—"
    if item.data_quality_issue_codes:
        evidence = ", ".join(_format_code(code) for code in item.data_quality_issue_codes)
    elif item.review_status is not None:
        evidence = f"review status {_format_code(item.review_status.value)}"
    elif item.detail is not None:
        evidence = _escape_table_cell(item.detail)
    else:
        evidence = "Recorded operational evidence"
    return (
        f"| {item.handling_state.value} | {item.kind.value} | "
        f"{when} | {asset} | {_format_code(scope)} | {evidence} |"
    )


def _format_code_list(values: Sequence[str]) -> str:
    if not values:
        return "Not recorded"
    return ", ".join(_format_code(value) for value in values)


def _format_snapshot_list(values: Sequence[SourceSnapshotEvidence]) -> str:
    if not values:
        return "Not recorded"
    return ", ".join(
        f"{_format_code(value.name)} · {_format_code(value.sha256)}" for value in values
    )


def _format_optional_time(value: datetime | None) -> str:
    return "Not recorded" if value is None else value.isoformat()


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _format_code(value: str) -> str:
    fence = "`"
    while fence in value:
        fence += "`"
    return f"{fence}{value}{fence}"
