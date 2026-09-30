import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from datetime import UTC, datetime
    from pathlib import Path

    import marimo as mo

    from industrial_phm.application import (
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonPhaseUnbalanceRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        JsonWindowAnalysisRuntimeRepository,
        SourceType,
        SystemStateErrorEvidence,
        build_acquisition_telemetry_surface,
        build_operations_attention_queue,
        build_operations_monitor_view,
        build_operations_overview,
        validate_distinct_source_state_paths,
    )
    from industrial_phm.presentation import (
        operations_v2_theme_css,
        render_monitor_assets_html,
        render_monitor_flow_html,
    )
    from industrial_phm.runtime import (
        SqliteAcquisitionSpool,
        SqliteAcquisitionSpoolConfig,
        SqliteAcquisitionTelemetryRepository,
    )

    return (
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonPhaseUnbalanceRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        JsonWindowAnalysisRuntimeRepository,
        Path,
        SourceType,
        SqliteAcquisitionSpool,
        SqliteAcquisitionSpoolConfig,
        SqliteAcquisitionTelemetryRepository,
        SystemStateErrorEvidence,
        UTC,
        build_acquisition_telemetry_surface,
        build_operations_attention_queue,
        build_operations_monitor_view,
        build_operations_overview,
        datetime,
        mo,
        operations_v2_theme_css,
        os,
        render_monitor_assets_html,
        render_monitor_flow_html,
        validate_distinct_source_state_paths,
    )


@app.cell
def _(mo):
    navigation = mo.ui.radio(
        options=[
            "Monitor",
            "Assets",
            "Investigations",
            "Maintenance",
            "System",
            "Setup",
        ],
        value="Monitor",
        label="",
    )
    refresh_button = mo.ui.run_button(label="Refresh")
    return navigation, refresh_button


@app.cell
def _(
    JsonFieldFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonPhaseUnbalanceRepository,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    JsonWindowAnalysisRuntimeRepository,
    Path,
    SourceType,
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    SystemStateErrorEvidence,
    UTC,
    build_acquisition_telemetry_surface,
    build_operations_attention_queue,
    build_operations_monitor_view,
    build_operations_overview,
    datetime,
    os,
    refresh_button,
    validate_distinct_source_state_paths,
):
    _refresh = refresh_button.value
    del _refresh
    assessed_at = datetime.now(UTC)

    registry_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY",
            "artifacts/operations/source-registry.json",
        )
    )
    source_runtime_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_SOURCE_RUNTIME",
            "artifacts/operations/source-runtime.json",
        )
    )
    acquisition_telemetry_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_TELEMETRY",
            "artifacts/operations/acquisition-telemetry.sqlite",
        )
    )
    acquisition_spool_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_SPOOL",
            "artifacts/operations/acquisition-spool.sqlite",
        )
    )
    field_analysis_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_STATE",
            "artifacts/operations/field-analysis.json",
        )
    )
    phase_analysis_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_PHASE_UNBALANCE_STATE",
            "artifacts/operations/phase-unbalance.json",
        )
    )
    analysis_runtime_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_RUNTIME",
            str(
                phase_analysis_path.with_name(
                    f"{phase_analysis_path.stem}-runtime.json"
                )
            ),
        )
    )
    finding_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_FINDING_STATE",
            "artifacts/operations/findings.json",
        )
    )
    review_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_MAINTENANCE_REVIEW_STATE",
            "artifacts/operations/finding-review.json",
        )
    )

    system_errors = []

    try:
        source_repository = JsonSourceRepository(registry_path)
        registered_sources = source_repository.list_sources()
        lifecycle_records = tuple(
            source_repository.get_lifecycle(source.source_id)
            for source in registered_sources
        )
        freshness_policies = tuple(
            policy
            for source in registered_sources
            if (policy := source_repository.get_freshness_policy(source.source_id))
            is not None
        )
    except (OSError, ValueError) as error:
        registered_sources = ()
        lifecycle_records = ()
        freshness_policies = ()
        system_errors.append(
            SystemStateErrorEvidence(
                "source-settings",
                str(error),
                assessed_at,
            )
        )

    try:
        validate_distinct_source_state_paths(registry_path, source_runtime_path)
        source_runtime_repository = JsonSourceRuntimeRepository(source_runtime_path)
        source_ids = {source.source_id for source in registered_sources}
        receipts = tuple(
            item
            for item in source_runtime_repository.list_latest_receipts()
            if item.source_id in source_ids
        )
        connection_attempts = tuple(
            item
            for item in source_runtime_repository.list_latest_connection_attempts()
            if item.source_id in source_ids
        )
    except (OSError, ValueError) as error:
        receipts = ()
        connection_attempts = ()
        system_errors.append(
            SystemStateErrorEvidence(
                "source-runtime",
                str(error),
                assessed_at,
            )
        )

    field_results = ()
    try:
        field_results = JsonFieldFeatureAnalysisRepository(field_analysis_path).list_results()
    except (OSError, ValueError) as error:
        system_errors.append(
            SystemStateErrorEvidence(
                "field-analysis-results",
                str(error),
                assessed_at,
            )
        )

    phase_results = ()
    try:
        phase_results = JsonPhaseUnbalanceRepository(phase_analysis_path).list_results()
    except (OSError, ValueError) as error:
        system_errors.append(
            SystemStateErrorEvidence(
                "phase-analysis-results",
                str(error),
                assessed_at,
            )
        )

    analysis_results = tuple(
        sorted(
            (*field_results, *phase_results),
            key=lambda item: (item.run.completed_at, item.run.analysis_run_id),
        )
    )
    analysis_runs = tuple(item.run for item in analysis_results)

    try:
        findings = JsonOperationalFindingRepository(finding_path).list_findings()
    except (OSError, ValueError) as error:
        findings = ()
        system_errors.append(
            SystemStateErrorEvidence(
                "review-requests",
                str(error),
                assessed_at,
            )
        )

    try:
        review_events = JsonFindingReviewRepository(review_path).list_events()
    except (OSError, ValueError) as error:
        review_events = ()
        system_errors.append(
            SystemStateErrorEvidence(
                "maintenance-review",
                str(error),
                assessed_at,
            )
        )

    overview = build_operations_overview(
        sources=registered_sources,
        lifecycle_records=lifecycle_records,
        receipts=receipts,
        freshness_policies=freshness_policies,
        connection_attempts=connection_attempts,
        analysis_runs=analysis_runs,
        findings=findings,
        review_events=review_events,
        as_of=assessed_at,
    )

    acquisition_surfaces = []
    if acquisition_telemetry_path.is_file() and acquisition_spool_path.is_file():
        try:
            telemetry_repository = SqliteAcquisitionTelemetryRepository(
                acquisition_telemetry_path
            )
            spool_repository = SqliteAcquisitionSpool(
                SqliteAcquisitionSpoolConfig(path=acquisition_spool_path)
            )
            for source in registered_sources:
                if source.source_type != SourceType.OPCUA:
                    continue
                try:
                    acquisition_surfaces.append(
                        build_acquisition_telemetry_surface(
                            telemetry_repository,
                            spool_repository,
                            source.source_id,
                            sampled_at=assessed_at,
                        )
                    )
                except (LookupError, OSError, ValueError) as error:
                    system_errors.append(
                        SystemStateErrorEvidence(
                            f"live-data:{source.source_id}",
                            str(error),
                            assessed_at,
                        )
                    )
        except (OSError, ValueError) as error:
            system_errors.append(
                SystemStateErrorEvidence(
                    "live-data",
                    str(error),
                    assessed_at,
                )
            )

    analysis_runtime = None
    if analysis_runtime_path.is_file():
        try:
            analysis_runtime = JsonWindowAnalysisRuntimeRepository(
                analysis_runtime_path
            ).load()
        except (OSError, ValueError) as error:
            system_errors.append(
                SystemStateErrorEvidence(
                    "analysis-service",
                    str(error),
                    assessed_at,
                )
            )

    attention = build_operations_attention_queue(
        overview=overview,
        system_errors=tuple(system_errors),
    )
    monitor = build_operations_monitor_view(
        sources=registered_sources,
        overview=overview,
        attention=attention,
        acquisition_surfaces=tuple(acquisition_surfaces),
        analysis_runs=analysis_runs,
        analysis_runtime=analysis_runtime,
        as_of=assessed_at,
    )

    return (
        analysis_runtime_path,
        attention,
        monitor,
        registry_path,
        source_runtime_path,
    )


@app.cell
def _(
    analysis_runtime_path,
    attention,
    mo,
    monitor,
    navigation,
    operations_v2_theme_css,
    refresh_button,
    registry_path,
    render_monitor_assets_html,
    render_monitor_flow_html,
    source_runtime_path,
):
    theme = mo.Html(operations_v2_theme_css())

    header = mo.hstack(
        [
            mo.md(
                "# Operations\n\n"
                "설비 데이터 흐름과 분석·검토 상태를 한 곳에서 확인합니다."
            ),
            refresh_button,
        ],
        justify="space-between",
        align="start",
    )

    if attention.items:
        attention_rows = "\n".join(
            (
                f"| **{item.kind.value.replace('_', ' ').title()}** | "
                f"{'-' if item.asset_identity is None else item.asset_identity.asset_id} | "
                f"{'-' if item.occurred_at is None else item.occurred_at.isoformat()} |"
            )
            for item in attention.items[:8]
        )
        attention_view = mo.md(
            "### Needs attention\n\n"
            "| What | Asset | Since |\n"
            "| --- | --- | --- |\n"
            + attention_rows
        )
    else:
        attention_view = mo.md(
            "### Needs attention\n\n"
            "No current operational item requires review."
        )

    if monitor.activities:
        activity_rows = "\n".join(
            (
                f"| {item.occurred_at.isoformat()} | "
                f"{'-' if item.asset_id is None else item.asset_id} | "
                f"{item.title} |"
            )
            for item in monitor.activities[:8]
        )
        activity_view = mo.md(
            "### Recent activity\n\n"
            "| Time | Asset | Activity |\n"
            "| --- | --- | --- |\n"
            + activity_rows
        )
    else:
        activity_view = mo.md("### Recent activity\n\nNo recent activity recorded.")

    monitor_view = mo.vstack(
        [
            mo.Html(render_monitor_flow_html(monitor)),
            attention_view,
            mo.Html(render_monitor_assets_html(monitor)),
            activity_view,
        ],
        gap=1.3,
    )

    pages = {
        "Monitor": monitor_view,
        "Assets": mo.md(
            "## Assets\n\n"
            "Asset workspace is the next V2 migration surface. "
            "Monitor already uses the new asset summary read model."
        ),
        "Investigations": mo.md(
            "## Investigations\n\n"
            "Queue + detail migration will replace the legacy analysis dropdown."
        ),
        "Maintenance": mo.md(
            "## Maintenance\n\n"
            "Open / acknowledged / closed review work will move here."
        ),
        "System": mo.md(
            "## System\n\n"
            f"Source settings: {registry_path}  \n"
            f"Source runtime: {source_runtime_path}  \n"
            f"Analysis service status: {analysis_runtime_path}  \n\n"
            "Technical paths are intentionally kept out of Monitor."
        ),
        "Setup": mo.md(
            "## Setup\n\n"
            "Source connection, signal mapping and measurement semantics will move here."
        ),
    }

    sidebar = mo.vstack(
        [
            mo.md("**INDUSTRIAL PHM**"),
            navigation,
        ],
        gap=1.0,
    )

    shell = mo.hstack(
        [
            sidebar,
            mo.vstack([header, pages[navigation.value]], gap=1.4),
        ],
        widths=[0.18, 0.82],
        align="start",
        gap=1.5,
    )
    mo.vstack([theme, shell], gap=0.0)
    return


if __name__ == "__main__":
    app.run()
