"""Pure Operations presenters without marimo or UI-framework dependencies."""

from __future__ import annotations

from datetime import datetime

from industrial_phm.application.observation import AssetObservationSummary
from industrial_phm.application.operations_attention import (
    AttentionItem,
    OperationsAttentionQueue,
)
from industrial_phm.application.operations_overview import OperationsOverview
from industrial_phm.application.source_health import SourceDataFlowState


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


def _format_optional_time(value: datetime | None) -> str:
    return "Not recorded" if value is None else value.isoformat()


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _format_code(value: str) -> str:
    fence = "`"
    while fence in value:
        fence += "`"
    return f"{fence}{value}{fence}"
