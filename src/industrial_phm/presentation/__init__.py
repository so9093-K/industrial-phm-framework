"""Presentation helpers for product-facing application read models."""

from industrial_phm.presentation.operations_analysis import (
    OperationalAnalysisPresentationKind,
    operational_analysis_presentation_kind,
    render_analysis_quality_markdown,
)
from industrial_phm.presentation.operations_assets import (
    asset_workspace_css,
    render_asset_analysis_html,
    render_asset_events_html,
    render_asset_header_html,
    render_asset_maintenance_html,
    render_asset_overview_html,
)
from industrial_phm.presentation.operations_investigations import (
    investigation_capability_label,
    investigation_queue_option_label,
    investigation_review_label,
    investigation_workspace_css,
    render_investigation_evidence_identity_html,
    render_investigation_summary_html,
)
from industrial_phm.presentation.operations_maintenance import (
    maintenance_capability_label,
    maintenance_queue_label,
    maintenance_status_label,
    maintenance_workspace_css,
    render_maintenance_identity_html,
    render_maintenance_summary_html,
    render_maintenance_timeline_html,
)
from industrial_phm.presentation.operations_setup import (
    lifecycle_action_label,
    render_setup_signals_html,
    render_setup_source_detail_html,
    render_setup_sources_html,
    setup_workspace_css,
)
from industrial_phm.presentation.operations_shell import (
    OPERATIONS_MAIN_BACKGROUND,
    OPERATIONS_PAGE_OPTIONS,
    initial_operations_page,
    operations_theme_css,
    render_monitor_asset_context_html,
    render_monitor_assets_html,
    render_monitor_flow_html,
    render_monitor_signal_overview_html,
    status_label,
)
from industrial_phm.presentation.operations_system import (
    render_system_diagnostics_html,
    render_system_errors_html,
    render_system_runtime_html,
    system_workspace_css,
)

__all__ = [
    "OPERATIONS_MAIN_BACKGROUND",
    "OPERATIONS_PAGE_OPTIONS",
    "OperationalAnalysisPresentationKind",
    "asset_workspace_css",
    "initial_operations_page",
    "investigation_capability_label",
    "investigation_queue_option_label",
    "investigation_review_label",
    "investigation_workspace_css",
    "lifecycle_action_label",
    "maintenance_capability_label",
    "maintenance_queue_label",
    "maintenance_status_label",
    "maintenance_workspace_css",
    "operational_analysis_presentation_kind",
    "operations_theme_css",
    "render_analysis_quality_markdown",
    "render_asset_analysis_html",
    "render_asset_events_html",
    "render_asset_header_html",
    "render_asset_maintenance_html",
    "render_asset_overview_html",
    "render_investigation_evidence_identity_html",
    "render_investigation_summary_html",
    "render_maintenance_identity_html",
    "render_maintenance_summary_html",
    "render_maintenance_timeline_html",
    "render_monitor_asset_context_html",
    "render_monitor_assets_html",
    "render_monitor_flow_html",
    "render_monitor_signal_overview_html",
    "render_setup_signals_html",
    "render_setup_source_detail_html",
    "render_setup_sources_html",
    "render_system_diagnostics_html",
    "render_system_errors_html",
    "render_system_runtime_html",
    "setup_workspace_css",
    "status_label",
    "system_workspace_css",
]
