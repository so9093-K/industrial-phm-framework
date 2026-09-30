"""Presentation helpers for product-facing application read models."""

from industrial_phm.presentation.operations import (
    OperationalAnalysisPresentationKind,
    operational_analysis_presentation_kind,
    render_analysis_quality_markdown,
    render_asset_analysis_markdown,
    render_asset_findings_markdown,
    render_asset_sources_markdown,
    render_asset_timeline_markdown,
    render_attention_queue_markdown,
    render_collection_monitor_markdown,
    render_data_quality_issues_markdown,
    render_observation_markdown,
    render_observation_provenance_markdown,
    render_source_data_flow_markdown,
    render_unplaced_asset_evidence_markdown,
)
from industrial_phm.presentation.operations_v2 import (
    OPERATIONS_V2_MAIN_BACKGROUND,
    operations_v2_theme_css,
    render_monitor_assets_html,
    render_monitor_flow_html,
    status_label,
)

__all__ = [
    "OPERATIONS_V2_MAIN_BACKGROUND",
    "OperationalAnalysisPresentationKind",
    "operational_analysis_presentation_kind",
    "operations_v2_theme_css",
    "render_analysis_quality_markdown",
    "render_asset_analysis_markdown",
    "render_asset_findings_markdown",
    "render_asset_sources_markdown",
    "render_asset_timeline_markdown",
    "render_attention_queue_markdown",
    "render_collection_monitor_markdown",
    "render_data_quality_issues_markdown",
    "render_monitor_assets_html",
    "render_monitor_flow_html",
    "render_observation_markdown",
    "render_observation_provenance_markdown",
    "render_source_data_flow_markdown",
    "render_unplaced_asset_evidence_markdown",
    "status_label",
]
