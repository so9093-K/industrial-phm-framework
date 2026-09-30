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
        AcquisitionTelemetrySurface,
        AssetIdentity,
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonPhaseUnbalanceRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        JsonWindowAnalysisRuntimeRepository,
        SourceType,
        SystemStateErrorEvidence,
        build_asset_detail,
        build_investigation_queue,
        build_maintenance_queue,
        build_operations_attention_queue,
        build_operations_monitor_view,
        build_operations_overview,
        build_system_runtime_view,
        create_human_review_finding,
        validate_distinct_source_state_paths,
    )
    from industrial_phm.application.maintenance_review import (
        FindingReviewAction,
        FindingReviewStatus,
        create_finding_review_event,
    )
    from industrial_phm.application.measurement_history import resolve_measurement_range
    from industrial_phm.application.operations_v2_assets import build_asset_workspace_view
    from industrial_phm.application.operations_v2_investigations import (
        InvestigationReviewState,
    )
    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
    from industrial_phm.presentation import (
        OperationalAnalysisPresentationKind,
        operational_analysis_presentation_kind,
        operations_v2_theme_css,
        render_analysis_quality_markdown,
        render_monitor_assets_html,
        render_monitor_flow_html,
        render_system_diagnostics_html,
        render_system_errors_html,
        render_system_runtime_html,
        system_workspace_css,
    )
    from industrial_phm.presentation.measurement_history import (
        latest_measurement_rows,
        measurement_aggregation_rows,
        measurement_aggregation_summary,
        measurement_history_range_summary,
        measurement_history_rows,
        render_measurement_aggregation_svg,
        render_measurement_history_svg,
    )
    from industrial_phm.presentation.operations_v2_assets import (
        asset_workspace_css,
        render_asset_analysis_html,
        render_asset_events_html,
        render_asset_header_html,
        render_asset_maintenance_html,
        render_asset_overview_html,
    )
    from industrial_phm.presentation.operations_v2_investigations import (
        investigation_capability_label,
        investigation_queue_option_label,
        investigation_review_label,
        investigation_workspace_css,
        render_investigation_evidence_identity_html,
        render_investigation_summary_html,
    )
    from industrial_phm.presentation.operations_v2_maintenance import (
        maintenance_queue_label,
        maintenance_status_label,
        maintenance_workspace_css,
        render_maintenance_identity_html,
        render_maintenance_summary_html,
        render_maintenance_timeline_html,
    )
    from industrial_phm.presentation.phase_unbalance import (
        phase_unbalance_exclusion_rows,
        phase_unbalance_provenance_rows,
        phase_unbalance_summary_rows,
        render_phase_unbalance_svg,
    )
    from industrial_phm.runtime import (
        SqliteAcquisitionSpool,
        SqliteAcquisitionSpoolConfig,
        SqliteAcquisitionTelemetryRepository,
    )

    return (
        AcquisitionTelemetrySurface,
        AssetIdentity,
        DuckLakeAssetHistory,
        DuckLakeAssetHistoryConfig,
        FindingReviewAction,
        FindingReviewStatus,
        InvestigationReviewState,
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonPhaseUnbalanceRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        JsonWindowAnalysisRuntimeRepository,
        OperationalAnalysisPresentationKind,
        Path,
        SourceType,
        SqliteAcquisitionSpool,
        SqliteAcquisitionSpoolConfig,
        SqliteAcquisitionTelemetryRepository,
        SystemStateErrorEvidence,
        UTC,
        asset_workspace_css,
        build_asset_detail,
        build_asset_workspace_view,
        build_investigation_queue,
        build_maintenance_queue,
        build_operations_attention_queue,
        build_operations_monitor_view,
        build_operations_overview,
        build_system_runtime_view,
        create_finding_review_event,
        create_human_review_finding,
        datetime,
        investigation_capability_label,
        investigation_queue_option_label,
        investigation_review_label,
        investigation_workspace_css,
        latest_measurement_rows,
        maintenance_queue_label,
        maintenance_status_label,
        maintenance_workspace_css,
        measurement_aggregation_rows,
        measurement_aggregation_summary,
        measurement_history_range_summary,
        measurement_history_rows,
        mo,
        operational_analysis_presentation_kind,
        operations_v2_theme_css,
        os,
        phase_unbalance_exclusion_rows,
        phase_unbalance_provenance_rows,
        phase_unbalance_summary_rows,
        render_analysis_quality_markdown,
        render_asset_analysis_html,
        render_asset_events_html,
        render_asset_header_html,
        render_asset_maintenance_html,
        render_asset_overview_html,
        render_investigation_evidence_identity_html,
        render_investigation_summary_html,
        render_maintenance_identity_html,
        render_maintenance_summary_html,
        render_maintenance_timeline_html,
        render_measurement_aggregation_svg,
        render_measurement_history_svg,
        render_monitor_assets_html,
        render_monitor_flow_html,
        render_phase_unbalance_svg,
        render_system_diagnostics_html,
        render_system_errors_html,
        render_system_runtime_html,
        resolve_measurement_range,
        system_workspace_css,
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
    DuckLakeAssetHistory,
    DuckLakeAssetHistoryConfig,
    JsonFieldFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonPhaseUnbalanceRepository,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    AcquisitionTelemetrySurface,
    JsonWindowAnalysisRuntimeRepository,
    Path,
    SourceType,
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    SystemStateErrorEvidence,
    UTC,
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
            str(phase_analysis_path.with_name(f"{phase_analysis_path.stem}-runtime.json")),
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
    history_catalog_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_HISTORY_CATALOG",
            "artifacts/operations/history/catalog.sqlite",
        )
    )
    history_data_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_HISTORY_DATA",
            "artifacts/operations/history/data",
        )
    )

    system_errors = []

    try:
        source_repository = JsonSourceRepository(registry_path)
        registered_sources = source_repository.list_sources()
        lifecycle_records = tuple(
            source_repository.get_lifecycle(source.source_id) for source in registered_sources
        )
        freshness_policies = tuple(
            policy
            for source in registered_sources
            if (policy := source_repository.get_freshness_policy(source.source_id)) is not None
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
            telemetry_repository = SqliteAcquisitionTelemetryRepository(acquisition_telemetry_path)
            spool_repository = SqliteAcquisitionSpool(
                SqliteAcquisitionSpoolConfig(path=acquisition_spool_path)
            )
            spool_snapshot = spool_repository.telemetry_snapshot(sampled_at=assessed_at)
            for source in registered_sources:
                if source.source_type != SourceType.OPCUA:
                    continue
                try:
                    acquisition_surfaces.append(
                        AcquisitionTelemetrySurface(
                            source=telemetry_repository.get(source.source_id),
                            spool=spool_snapshot,
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
            analysis_runtime = JsonWindowAnalysisRuntimeRepository(analysis_runtime_path).load()
        except (OSError, ValueError) as error:
            system_errors.append(
                SystemStateErrorEvidence(
                    "analysis-service",
                    str(error),
                    assessed_at,
                )
            )

    history_reader = None
    history_assets = ()
    if history_catalog_path.is_file():
        try:
            history_reader = DuckLakeAssetHistory(
                DuckLakeAssetHistoryConfig(history_catalog_path, history_data_path)
            )
            history_assets = history_reader.list_history_assets()
        except Exception as error:
            system_errors.append(
                SystemStateErrorEvidence(
                    "asset-history",
                    str(error),
                    assessed_at,
                )
            )
            history_reader = None

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

    system_diagnostics = (
        ("Source registry", str(registry_path)),
        ("Source runtime", str(source_runtime_path)),
        ("Acquisition telemetry", str(acquisition_telemetry_path)),
        ("Acquisition spool", str(acquisition_spool_path)),
        ("Asset History catalog", str(history_catalog_path)),
        ("Asset History data", str(history_data_path)),
        ("Vibration analysis", str(field_analysis_path)),
        ("Three-phase analysis", str(phase_analysis_path)),
        ("Analysis service runtime", str(analysis_runtime_path)),
        ("Review requests", str(finding_path)),
        ("Maintenance review", str(review_path)),
    )

    return (
        acquisition_surfaces,
        analysis_results,
        analysis_runtime,
        assessed_at,
        finding_path,
        findings,
        history_assets,
        history_reader,
        monitor,
        overview,
        registered_sources,
        review_events,
        review_path,
        system_diagnostics,
        system_errors,
    )


@app.cell
def _():
    asset_selection = {"asset_id": None}
    return (asset_selection,)


@app.cell
def _(asset_selection, history_assets, mo, monitor):
    _asset_ids = tuple(
        sorted(
            {
                *(item.asset_id for item in monitor.assets),
                *(item.asset_id for item in history_assets),
            }
        )
    )
    if _asset_ids:
        _selected_asset_id = (
            asset_selection["asset_id"]
            if asset_selection["asset_id"] in _asset_ids
            else _asset_ids[0]
        )
        asset_selector = mo.ui.dropdown(
            options=list(_asset_ids),
            value=_selected_asset_id,
            label="Asset",
            full_width=True,
            on_change=lambda value: asset_selection.update(asset_id=value),
        )
    else:
        asset_selector = None
    asset_section = mo.ui.radio(
        options=["Overview", "Signals", "Analysis", "Events", "Maintenance"],
        value="Overview",
        label="View",
    )
    return asset_section, asset_selector


@app.cell
def _(
    AssetIdentity,
    acquisition_surfaces,
    analysis_results,
    asset_selector,
    build_asset_detail,
    build_asset_workspace_view,
    findings,
    history_assets,
    history_reader,
    monitor,
    navigation,
    overview,
    registered_sources,
    review_events,
):
    asset_workspace = None
    asset_workspace_error = None
    asset_history_error = None
    if navigation.value == "Assets" and asset_selector is not None:
        _selected_asset_id = asset_selector.value
        _history_summary = next(
            (item for item in history_assets if item.asset_id == _selected_asset_id),
            None,
        )
        _history_channels = ()
        if history_reader is not None:
            try:
                _history_channels = history_reader.list_history_channels(_selected_asset_id)
            except Exception as error:
                asset_history_error = str(error)
        try:
            _detail = build_asset_detail(
                AssetIdentity(_selected_asset_id),
                sources=registered_sources,
                overview=overview,
                analysis_runs=tuple(item.run for item in analysis_results),
                findings=findings,
                review_events=review_events,
            )
            _monitor_asset = next(
                (item for item in monitor.assets if item.asset_id == _selected_asset_id),
                None,
            )
            _asset_source_ids = {item.source.source_id for item in _detail.source_contexts}
            _asset_surfaces = tuple(
                item for item in acquisition_surfaces if item.source.source_id in _asset_source_ids
            )
            asset_workspace = build_asset_workspace_view(
                asset_id=_selected_asset_id,
                detail=_detail,
                analysis_results=analysis_results,
                monitor_asset=_monitor_asset,
                history_summary=_history_summary,
                history_channels=_history_channels,
                acquisition_surfaces=_asset_surfaces,
            )
        except Exception as error:
            asset_workspace_error = str(error)
    return asset_history_error, asset_workspace, asset_workspace_error


@app.cell
def _(asset_workspace, mo):
    if asset_workspace is None or not asset_workspace.history_channels:
        signal_channel_selector = None
    else:
        signal_channel_selector = mo.ui.dropdown(
            options=list(asset_workspace.history_channels),
            value=asset_workspace.history_channels[0],
            label="Signal",
            full_width=True,
        )
    signal_range_selector = mo.ui.radio(
        options=["15m", "24h", "7d"],
        value="15m",
        label="Time range",
    )
    return signal_channel_selector, signal_range_selector


@app.cell
def _(
    asset_history_error,
    asset_selector,
    asset_workspace,
    assessed_at,
    history_reader,
    latest_measurement_rows,
    measurement_aggregation_rows,
    measurement_aggregation_summary,
    measurement_history_range_summary,
    measurement_history_rows,
    mo,
    navigation,
    render_measurement_aggregation_svg,
    render_measurement_history_svg,
    resolve_measurement_range,
    signal_channel_selector,
    signal_range_selector,
):
    if navigation.value != "Assets":
        signal_view = mo.md("")
    elif asset_workspace is None:
        signal_view = mo.md("No asset is selected.")
    elif asset_history_error:
        signal_view = mo.callout(
            asset_history_error,
            kind="danger",
            title="Asset History unavailable",
        )
    elif history_reader is None:
        signal_view = mo.md(
            "### Signals\n\nNo Asset History catalog is available for this workspace."
        )
    elif signal_channel_selector is None:
        signal_view = mo.md("### Signals\n\nNo stored signal is available for this asset yet.")
    elif asset_selector is None:
        signal_view = mo.md("### Signals\n\nNo asset is selected.")
    else:
        try:
            _channel_id = signal_channel_selector.value
            _range_id = signal_range_selector.value
            _start_at, _end_at = resolve_measurement_range(
                _range_id,
                as_of=assessed_at,
                start_at=assessed_at,
                end_at=assessed_at,
            )
            _latest = history_reader.query_latest_measurements(
                asset_selector.value,
                channel_id=_channel_id,
            )
            _latest_rows = latest_measurement_rows(_latest, as_of=assessed_at)
            _controls = mo.hstack(
                [signal_channel_selector, signal_range_selector],
                widths=[0.62, 0.38],
                align="start",
            )
            _latest_view = mo.vstack(
                [
                    mo.md("#### Latest stored value"),
                    mo.ui.table(
                        [
                            {
                                "Source": row["source"],
                                "Point": row["measurement_point"],
                                "Time": row["time"],
                                "Value": row["value"],
                                "Unit": row["unit"],
                                "Quality": row["quality"],
                                "Source quality": row["source_quality"],
                                "Time state": row["event_time_state"],
                                "History age (s)": row["history_age_seconds"],
                            }
                            for row in _latest_rows
                        ],
                        selection=None,
                    ),
                ],
                gap=0.6,
            )

            if _range_id in {"24h", "7d"}:
                _aggregation = history_reader.query_measurement_aggregation(
                    asset_selector.value,
                    channel_id=_channel_id,
                    start_at=_start_at,
                    end_at=_end_at,
                    bucket_count=100 if _range_id == "7d" else 200,
                )
                _trend_view = mo.vstack(
                    [
                        mo.Html(render_measurement_aggregation_svg(_aggregation)),
                        mo.ui.table(
                            [measurement_aggregation_summary(_aggregation)],
                            selection=None,
                        ),
                        mo.accordion(
                            {
                                "Data details": mo.ui.table(
                                    measurement_aggregation_rows(_aggregation),
                                    page_size=10,
                                )
                            }
                        ),
                    ],
                    gap=0.8,
                )
            else:
                _page = history_reader.query_measurement_page(
                    asset_selector.value,
                    start_at=_start_at,
                    end_at=_end_at,
                    channel_id=_channel_id,
                    point_budget=2000,
                    latest=True,
                )
                _trend_blocks = [
                    mo.ui.table(
                        [
                            measurement_history_range_summary(
                                _page,
                                start_at=_start_at,
                                end_at=_end_at,
                            )
                        ],
                        selection=None,
                    )
                ]
                if _page.points:
                    _trend_blocks.append(
                        mo.Html(
                            render_measurement_history_svg(
                                _page,
                                start_at=_start_at,
                                end_at=_end_at,
                            )
                        )
                    )
                    _trend_blocks.append(
                        mo.accordion(
                            {
                                "Raw observations": mo.ui.table(
                                    measurement_history_rows(_page),
                                    page_size=10,
                                )
                            }
                        )
                    )
                else:
                    _trend_blocks.append(
                        mo.md("No stored observation falls inside the selected time range.")
                    )
                _trend_view = mo.vstack(_trend_blocks, gap=0.8)

            signal_view = mo.vstack(
                [
                    _controls,
                    _latest_view,
                    _trend_view,
                    mo.md(
                        "Stored measurements and UI aggregates are observation evidence. "
                        "This view does not infer asset health, fault, alarm, or missing samples."
                    ),
                ],
                gap=1.0,
            )
        except Exception as error:
            signal_view = mo.callout(
                str(error),
                kind="danger",
                title="Signals unavailable",
            )
    return (signal_view,)


@app.cell
def _():
    investigation_selection = {"investigation_id": None}
    return (investigation_selection,)


@app.cell
def _(findings, mo, review_events):
    get_review_workflow, set_review_workflow = mo.state((findings, review_events))
    get_review_request_error, set_review_request_error = mo.state("")
    get_review_request_success, set_review_request_success = mo.state("")
    return (
        get_review_request_error,
        get_review_request_success,
        get_review_workflow,
        set_review_request_error,
        set_review_request_success,
        set_review_workflow,
    )


@app.cell
def _(
    findings,
    refresh_button,
    review_events,
    set_review_request_error,
    set_review_request_success,
    set_review_workflow,
):
    if refresh_button.value:
        set_review_workflow((findings, review_events))
        set_review_request_error("")
        set_review_request_success("")
    return


@app.cell
def _(
    analysis_results,
    build_investigation_queue,
    get_review_workflow,
):
    investigation_findings, maintenance_events = get_review_workflow()
    investigation_queue = build_investigation_queue(
        analysis_results=analysis_results,
        findings=investigation_findings,
        review_events=maintenance_events,
    )
    return investigation_findings, maintenance_events, investigation_queue


@app.cell
def _(
    InvestigationReviewState,
    investigation_capability_label,
    investigation_queue,
    investigation_review_label,
    mo,
):
    _review_options = ["All"] + [
        investigation_review_label(state) for state in InvestigationReviewState
    ]
    investigation_review_filter = mo.ui.dropdown(
        options=_review_options,
        value="All",
        label="Review",
        full_width=True,
    )
    investigation_asset_filter = mo.ui.dropdown(
        options=["All", *investigation_queue.asset_ids],
        value="All",
        label="Asset",
        full_width=True,
    )
    _capability_labels = {
        investigation_capability_label(capability_id): capability_id
        for capability_id in investigation_queue.capability_ids
    }
    investigation_capability_filter = mo.ui.dropdown(
        options=["All", *_capability_labels],
        value="All",
        label="Capability",
        full_width=True,
    )
    return (
        investigation_asset_filter,
        investigation_capability_filter,
        investigation_review_filter,
    )


@app.cell
def _(
    InvestigationReviewState,
    investigation_asset_filter,
    investigation_capability_filter,
    investigation_capability_label,
    investigation_queue,
    investigation_queue_option_label,
    investigation_review_filter,
    investigation_review_label,
    investigation_selection,
    mo,
):
    _review_state_by_label = {
        investigation_review_label(state): state for state in InvestigationReviewState
    }
    _capability_by_label = {
        investigation_capability_label(capability_id): capability_id
        for capability_id in investigation_queue.capability_ids
    }
    _filtered_investigations = investigation_queue.filter(
        review_state=_review_state_by_label.get(investigation_review_filter.value),
        asset_id=(
            None if investigation_asset_filter.value == "All" else investigation_asset_filter.value
        ),
        capability_id=_capability_by_label.get(investigation_capability_filter.value),
    )
    _label_to_id = {
        f"{investigation_queue_option_label(item)} · {index + 1}": item.investigation_id
        for index, item in enumerate(_filtered_investigations)
    }
    _id_to_label = {value: key for key, value in _label_to_id.items()}
    if _filtered_investigations:
        _selected_id = (
            investigation_selection["investigation_id"]
            if investigation_selection["investigation_id"] in _id_to_label
            else _filtered_investigations[0].investigation_id
        )
        investigation_selection["investigation_id"] = _selected_id
        investigation_selector = mo.ui.radio(
            options=list(_label_to_id),
            value=_id_to_label[_selected_id],
            label="Queue",
            on_change=lambda value: investigation_selection.update(
                investigation_id=_label_to_id[value]
            ),
        )
    else:
        investigation_selector = None
    investigation_filtered_count = len(_filtered_investigations)
    investigation_selected_id = (
        None if investigation_selector is None else _label_to_id[investigation_selector.value]
    )
    return (
        investigation_filtered_count,
        investigation_selected_id,
        investigation_selector,
    )


@app.cell
def _(
    analysis_results,
    investigation_queue,
    investigation_selected_id,
):
    selected_investigation = None
    selected_investigation_result = None
    if investigation_selected_id is not None:
        selected_investigation = next(
            (
                item
                for item in investigation_queue.items
                if item.investigation_id == investigation_selected_id
            ),
            None,
        )
        if selected_investigation is not None:
            selected_investigation_result = next(
                (
                    result
                    for result in analysis_results
                    if result.run.analysis_run_id == selected_investigation.analysis_run_id
                    and result.evidence.capability_id == selected_investigation.capability_id
                ),
                None,
            )
    return selected_investigation, selected_investigation_result


@app.cell
def _(InvestigationReviewState, mo, selected_investigation):
    if (
        selected_investigation is not None
        and selected_investigation.review_state == InvestigationReviewState.NOT_REQUESTED
    ):
        request_review_button = mo.ui.run_button(
            label="Request review",
            kind="warn",
        )
    else:
        request_review_button = None
    return (request_review_button,)


@app.cell
def _(
    JsonOperationalFindingRepository,
    create_human_review_finding,
    finding_path,
    request_review_button,
    get_review_workflow,
    selected_investigation_result,
    set_review_request_error,
    set_review_request_success,
    set_review_workflow,
):
    if request_review_button is not None and request_review_button.value:
        try:
            if selected_investigation_result is None:
                raise ValueError("select an analysis result before requesting review")
            _finding = create_human_review_finding(selected_investigation_result)
            _repository = JsonOperationalFindingRepository(finding_path)
            _repository.record(_finding)
            _updated_findings = _repository.list_findings()
        except (OSError, ValueError) as error:
            set_review_request_error(str(error))
            set_review_request_success("")
        else:
            _, _current_events = get_review_workflow()
            set_review_workflow((_updated_findings, _current_events))
            set_review_request_error("")
            set_review_request_success(
                "Review requested. The analysis evidence itself was not reinterpreted."
            )
    return


@app.cell
def _(get_review_request_error, get_review_request_success):
    review_request_error = get_review_request_error()
    review_request_success = get_review_request_success()
    return review_request_error, review_request_success


@app.cell
def _(
    OperationalAnalysisPresentationKind,
    investigation_asset_filter,
    investigation_capability_filter,
    investigation_filtered_count,
    investigation_queue,
    investigation_review_filter,
    investigation_review_label,
    investigation_selector,
    mo,
    operational_analysis_presentation_kind,
    phase_unbalance_exclusion_rows,
    phase_unbalance_provenance_rows,
    phase_unbalance_summary_rows,
    render_analysis_quality_markdown,
    render_investigation_evidence_identity_html,
    render_investigation_summary_html,
    render_phase_unbalance_svg,
    request_review_button,
    review_request_error,
    review_request_success,
    selected_investigation,
    selected_investigation_result,
):
    _filters = mo.hstack(
        [
            investigation_review_filter,
            investigation_asset_filter,
            investigation_capability_filter,
        ],
        widths=[0.30, 0.34, 0.36],
        align="start",
    )

    if investigation_selector is None:
        _queue_panel = mo.vstack(
            [
                _filters,
                mo.md("### Queue\n\nNo saved analysis result matches the current filters."),
            ],
            gap=0.8,
        )
    else:
        _queue_panel = mo.vstack(
            [
                _filters,
                mo.md(
                    f"### Queue\n\n"
                    f"{investigation_filtered_count} shown · "
                    f"{len(investigation_queue.items)} saved"
                ),
                investigation_selector,
                mo.md(
                    "Review state describes the human workflow only. "
                    "Queue order is newest analysis first, not severity."
                ),
            ],
            gap=0.8,
        )

    if selected_investigation is None or selected_investigation_result is None:
        _detail_panel = mo.md(
            "## Investigation detail\n\nSelect an analysis result from the queue."
        )
    else:
        _presentation_kind = operational_analysis_presentation_kind(
            selected_investigation.capability_id
        )
        _evidence_blocks = [
            mo.Html(render_investigation_summary_html(selected_investigation)),
            mo.md(render_analysis_quality_markdown(selected_investigation_result.run)),
        ]

        if _presentation_kind == OperationalAnalysisPresentationKind.PHASE_UNBALANCE:
            _evidence_blocks.extend(
                [
                    mo.md("### Evidence summary"),
                    mo.ui.table(
                        phase_unbalance_summary_rows(selected_investigation_result),
                        selection=None,
                    ),
                    mo.Html(render_phase_unbalance_svg(selected_investigation_result)),
                    mo.accordion(
                        {
                            "Excluded observations": mo.ui.table(
                                phase_unbalance_exclusion_rows(selected_investigation_result),
                                selection=None,
                                page_size=12,
                            ),
                            "Evidence & provenance": mo.ui.table(
                                phase_unbalance_provenance_rows(selected_investigation_result),
                                selection=None,
                                page_size=20,
                            ),
                        }
                    ),
                ]
            )
        elif _presentation_kind == OperationalAnalysisPresentationKind.VIBRATION_FEATURES:
            _evidence = selected_investigation_result.evidence
            _feature_rows = [
                {"Feature": name, "Value": value}
                for name, value in zip(
                    _evidence.feature_names,
                    _evidence.values,
                    strict=True,
                )
            ]
            _evidence_blocks.extend(
                [
                    mo.md("### Vibration feature evidence"),
                    mo.ui.table(_feature_rows, selection=None),
                    mo.md(
                        "These values are waveform statistics from one exact FILE snapshot. "
                        "No threshold or state policy interprets them here as anomaly, fault, "
                        "health, alert, or maintenance need."
                    ),
                ]
            )
        else:
            _evidence_blocks.append(
                mo.callout(
                    "This capability has persisted evidence but no explicit Operations "
                    "renderer. The evidence is not reinterpreted as another capability.",
                    kind="neutral",
                    title="Evidence renderer unavailable",
                )
            )

        _review_blocks = []
        if review_request_error:
            _review_blocks.append(
                mo.callout(
                    review_request_error,
                    kind="danger",
                    title="Review request failed",
                )
            )
        if review_request_success:
            _review_blocks.append(
                mo.callout(
                    review_request_success,
                    kind="success",
                    title="Review requested",
                )
            )
        if request_review_button is not None:
            _review_blocks.extend(
                [
                    mo.md("### Human review"),
                    request_review_button,
                    mo.md(
                        "Requesting review records a workflow item linked to this evidence. "
                        "It does not declare a fault, alarm, health state, or maintenance need."
                    ),
                ]
            )
        else:
            _review_blocks.append(
                mo.md(
                    "### Human review\n\n"
                    "Current workflow state: "
                    f"**{investigation_review_label(selected_investigation.review_state)}**"
                )
            )

        _detail_panel = mo.vstack(
            [
                *_evidence_blocks,
                *_review_blocks,
                mo.accordion(
                    {
                        "Evidence identity": mo.Html(
                            render_investigation_evidence_identity_html(selected_investigation)
                        )
                    }
                ),
            ],
            gap=0.9,
        )

    investigation_view = mo.hstack(
        [_queue_panel, _detail_panel],
        widths=[0.36, 0.64],
        align="start",
        gap=1.3,
    )
    return (investigation_view,)


@app.cell
def _():
    maintenance_selection = {"finding_id": None}
    return (maintenance_selection,)


@app.cell
def _(mo):
    get_maintenance_error, set_maintenance_error = mo.state("")
    get_maintenance_success, set_maintenance_success = mo.state("")
    return (
        get_maintenance_error,
        get_maintenance_success,
        set_maintenance_error,
        set_maintenance_success,
    )


@app.cell
def _(
    build_maintenance_queue,
    investigation_findings,
    maintenance_events,
):
    maintenance_queue = build_maintenance_queue(
        findings=investigation_findings,
        review_events=maintenance_events,
    )
    return (maintenance_queue,)


@app.cell
def _(FindingReviewStatus, maintenance_queue, maintenance_status_label, mo):
    _status_labels = ["All", *[maintenance_status_label(status) for status in FindingReviewStatus]]
    maintenance_status_filter = mo.ui.dropdown(
        options=_status_labels,
        value="All",
        label="Status",
        full_width=True,
    )
    maintenance_asset_filter = mo.ui.dropdown(
        options=["All", *maintenance_queue.asset_ids],
        value="All",
        label="Asset",
        full_width=True,
    )
    return maintenance_asset_filter, maintenance_status_filter


@app.cell
def _(
    FindingReviewStatus,
    maintenance_asset_filter,
    maintenance_queue,
    maintenance_queue_label,
    maintenance_selection,
    maintenance_status_filter,
    maintenance_status_label,
    mo,
):
    _status_by_label = {maintenance_status_label(status): status for status in FindingReviewStatus}
    _filtered = maintenance_queue.filter(
        status=_status_by_label.get(maintenance_status_filter.value),
        asset_id=(
            None if maintenance_asset_filter.value == "All" else maintenance_asset_filter.value
        ),
    )
    _label_to_id = {
        f"{maintenance_queue_label(item)} · {index + 1}": item.finding_id
        for index, item in enumerate(_filtered)
    }
    _id_to_label = {value: key for key, value in _label_to_id.items()}
    if _filtered:
        _selected_id = (
            maintenance_selection["finding_id"]
            if maintenance_selection["finding_id"] in _id_to_label
            else _filtered[0].finding_id
        )
        maintenance_selection["finding_id"] = _selected_id
        maintenance_selector = mo.ui.radio(
            options=list(_label_to_id),
            value=_id_to_label[_selected_id],
            label="Queue",
            on_change=lambda value: maintenance_selection.update(finding_id=_label_to_id[value]),
        )
        maintenance_selected_id = _label_to_id[maintenance_selector.value]
    else:
        maintenance_selector = None
        maintenance_selected_id = None
    maintenance_filtered_count = len(_filtered)
    return maintenance_filtered_count, maintenance_selected_id, maintenance_selector


@app.cell
def _(maintenance_queue, maintenance_selected_id):
    selected_maintenance = (
        None
        if maintenance_selected_id is None
        else next(
            (
                item
                for item in maintenance_queue.items
                if item.finding_id == maintenance_selected_id
            ),
            None,
        )
    )
    return (selected_maintenance,)


@app.cell
def _(FindingReviewStatus, mo, selected_maintenance):
    if selected_maintenance is None or selected_maintenance.status == FindingReviewStatus.CLOSED:
        maintenance_note_input = None
        maintenance_add_note_button = None
        maintenance_ack_button = None
        maintenance_close_button = None
    else:
        maintenance_note_input = mo.ui.text_area(
            value="",
            label="Review note",
            rows=3,
            full_width=True,
        )
        maintenance_add_note_button = mo.ui.run_button(label="Add note")
        maintenance_ack_button = (
            mo.ui.run_button(label="Acknowledge", kind="success")
            if selected_maintenance.status == FindingReviewStatus.OPEN
            else None
        )
        maintenance_close_button = (
            mo.ui.run_button(label="Close review", kind="warn")
            if selected_maintenance.status == FindingReviewStatus.ACKNOWLEDGED
            else None
        )
    return (
        maintenance_ack_button,
        maintenance_add_note_button,
        maintenance_close_button,
        maintenance_note_input,
    )


@app.cell
def _(
    FindingReviewAction,
    JsonFindingReviewRepository,
    create_finding_review_event,
    get_review_workflow,
    investigation_findings,
    maintenance_ack_button,
    maintenance_add_note_button,
    maintenance_close_button,
    maintenance_note_input,
    review_path,
    selected_maintenance,
    set_maintenance_error,
    set_maintenance_success,
    set_review_workflow,
):
    _action = None
    if maintenance_add_note_button is not None and maintenance_add_note_button.value:
        _action = FindingReviewAction.NOTE
    elif maintenance_ack_button is not None and maintenance_ack_button.value:
        _action = FindingReviewAction.ACKNOWLEDGE
    elif maintenance_close_button is not None and maintenance_close_button.value:
        _action = FindingReviewAction.CLOSE

    if _action is not None:
        try:
            if selected_maintenance is None:
                raise ValueError("select a review before recording an action")
            _finding = next(
                item
                for item in investigation_findings
                if item.finding_id == selected_maintenance.finding_id
            )
            _note = "" if maintenance_note_input is None else maintenance_note_input.value
            _event = create_finding_review_event(_finding, action=_action, note=_note)
            _repository = JsonFindingReviewRepository(review_path)
            _repository.record(_event)
            _events = _repository.list_events()
        except (LookupError, OSError, ValueError) as error:
            set_maintenance_error(str(error))
            set_maintenance_success("")
        else:
            _current_findings, _ = get_review_workflow()
            set_review_workflow((_current_findings, _events))
            set_maintenance_error("")
            set_maintenance_success(f"Review action recorded: {_action.value}.")
    return


@app.cell
def _(get_maintenance_error, get_maintenance_success):
    maintenance_error = get_maintenance_error()
    maintenance_success = get_maintenance_success()
    return maintenance_error, maintenance_success


@app.cell
def _(
    FindingReviewStatus,
    maintenance_ack_button,
    maintenance_add_note_button,
    maintenance_asset_filter,
    maintenance_close_button,
    maintenance_error,
    maintenance_filtered_count,
    maintenance_note_input,
    maintenance_queue,
    maintenance_selector,
    maintenance_status_filter,
    maintenance_success,
    maintenance_workspace_css,
    mo,
    render_maintenance_identity_html,
    render_maintenance_summary_html,
    render_maintenance_timeline_html,
    selected_maintenance,
):
    _counts = mo.md(
        "### Review workload\n\n"
        f"**Open {maintenance_queue.count(FindingReviewStatus.OPEN)}** · "
        f"Acknowledged {maintenance_queue.count(FindingReviewStatus.ACKNOWLEDGED)} · "
        f"Closed {maintenance_queue.count(FindingReviewStatus.CLOSED)}"
    )
    _filters = mo.hstack(
        [maintenance_status_filter, maintenance_asset_filter],
        widths=[0.45, 0.55],
        align="start",
    )
    if maintenance_selector is None:
        _queue_panel = mo.vstack(
            [_counts, _filters, mo.md("No review matches the current filters.")],
            gap=0.8,
        )
    else:
        _queue_panel = mo.vstack(
            [
                _counts,
                _filters,
                mo.md(
                    f"### Queue\n\n{maintenance_filtered_count} shown · "
                    f"{len(maintenance_queue.items)} total"
                ),
                maintenance_selector,
            ],
            gap=0.8,
        )

    if selected_maintenance is None:
        _detail_panel = mo.md("## Maintenance review\n\nSelect a review from the queue.")
    else:
        _action_blocks = []
        if maintenance_error:
            _action_blocks.append(
                mo.callout(maintenance_error, kind="danger", title="Review action failed")
            )
        if maintenance_success:
            _action_blocks.append(
                mo.callout(maintenance_success, kind="success", title="Review updated")
            )
        if selected_maintenance.status != FindingReviewStatus.CLOSED:
            _buttons = [
                button
                for button in (
                    maintenance_add_note_button,
                    maintenance_ack_button,
                    maintenance_close_button,
                )
                if button is not None
            ]
            _action_blocks.extend(
                [
                    mo.md("### Review actions"),
                    maintenance_note_input,
                    mo.hstack(_buttons, justify="start", gap=0.6),
                ]
            )
        else:
            _action_blocks.append(
                mo.md(
                    "### Review actions\n\n"
                    "This review is closed. Closed review history is append-locked."
                )
            )
        _detail_panel = mo.vstack(
            [
                mo.Html(render_maintenance_summary_html(selected_maintenance)),
                mo.Html(render_maintenance_timeline_html(selected_maintenance)),
                *_action_blocks,
                mo.accordion(
                    {
                        "Review identity": mo.Html(
                            render_maintenance_identity_html(selected_maintenance)
                        )
                    }
                ),
                mo.md(
                    "Acknowledge and Close change only the human review workflow. "
                    "They do not confirm a fault, repair, asset health, or CMMS work order."
                ),
            ],
            gap=0.9,
        )

    maintenance_view = mo.hstack(
        [_queue_panel, _detail_panel],
        widths=[0.36, 0.64],
        align="start",
        gap=1.3,
    )
    return (maintenance_view,)


@app.cell
def _(
    acquisition_surfaces,
    analysis_runtime,
    assessed_at,
    build_system_runtime_view,
    monitor,
    registered_sources,
    system_errors,
):
    system_runtime = build_system_runtime_view(
        monitor=monitor,
        sources=registered_sources,
        acquisition_surfaces=tuple(acquisition_surfaces),
        analysis_runtime=analysis_runtime,
        system_errors=tuple(system_errors),
        as_of=assessed_at,
    )
    return (system_runtime,)


@app.cell
def _(
    mo,
    render_system_diagnostics_html,
    render_system_errors_html,
    render_system_runtime_html,
    system_diagnostics,
    system_runtime,
):
    system_view = mo.vstack(
        [
            mo.Html(render_system_runtime_html(system_runtime)),
            mo.Html(render_system_errors_html(system_runtime)),
            mo.accordion(
                {
                    "Advanced diagnostics": mo.Html(
                        render_system_diagnostics_html(system_diagnostics)
                    )
                }
            ),
            mo.md(
                "Runtime status is shown only where current evidence exists. "
                "A missing process heartbeat is displayed as unavailable rather than "
                "assumed healthy."
            ),
        ],
        gap=1.0,
    )
    return (system_view,)


@app.cell
def _(
    asset_section,
    asset_selector,
    asset_workspace,
    asset_workspace_css,
    asset_workspace_error,
    investigation_view,
    investigation_workspace_css,
    maintenance_view,
    maintenance_workspace_css,
    mo,
    monitor,
    navigation,
    operations_v2_theme_css,
    refresh_button,
    render_asset_analysis_html,
    render_asset_events_html,
    render_asset_header_html,
    render_asset_maintenance_html,
    render_asset_overview_html,
    render_monitor_assets_html,
    render_monitor_flow_html,
    signal_view,
    system_view,
    system_workspace_css,
):
    theme = mo.Html(
        operations_v2_theme_css()
        + asset_workspace_css()
        + investigation_workspace_css()
        + maintenance_workspace_css()
        + system_workspace_css()
    )

    header = mo.hstack(
        [
            mo.md("# Operations\n\n설비 데이터 흐름과 분석·검토 상태를 한 곳에서 확인합니다."),
            refresh_button,
        ],
        widths=[0.82, 0.18],
        align="start",
    )

    if monitor.attention:
        attention_rows = "\n".join(
            (
                f"| **{item.title}** | "
                f"{'-' if item.asset_id is None else item.asset_id} | "
                f"{'-' if item.occurred_at is None else item.occurred_at.isoformat()} |"
            )
            for item in monitor.attention[:8]
        )
        attention_view = mo.md(
            "### Needs attention\n\n"
            "| What | Asset | Since |\n"
            "| --- | --- | --- |\n" + attention_rows
        )
    else:
        attention_view = mo.md(
            "### Needs attention\n\nNo current operational item requires review."
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
            "| --- | --- | --- |\n" + activity_rows
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

    if asset_selector is None:
        asset_view = mo.md(
            "## Assets\n\n"
            "No asset evidence is available yet. Add a source in Setup or load history."
        )
    elif asset_workspace_error:
        asset_view = mo.vstack(
            [
                asset_selector,
                mo.callout(
                    asset_workspace_error,
                    kind="danger",
                    title="Asset workspace unavailable",
                ),
            ],
            gap=1.0,
        )
    elif asset_workspace is None:
        asset_view = mo.vstack(
            [asset_selector, mo.md("Select Assets to load this workspace.")],
            gap=1.0,
        )
    else:
        _asset_sections = {
            "Overview": mo.Html(render_asset_overview_html(asset_workspace)),
            "Signals": signal_view,
            "Analysis": mo.Html(render_asset_analysis_html(asset_workspace)),
            "Events": mo.Html(render_asset_events_html(asset_workspace)),
            "Maintenance": mo.Html(render_asset_maintenance_html(asset_workspace)),
        }
        asset_view = mo.vstack(
            [
                mo.hstack(
                    [asset_selector, asset_section],
                    widths=[0.46, 0.54],
                    align="start",
                ),
                mo.Html(render_asset_header_html(asset_workspace)),
                _asset_sections[asset_section.value],
            ],
            gap=1.1,
        )

    pages = {
        "Monitor": monitor_view,
        "Assets": asset_view,
        "Investigations": investigation_view,
        "Maintenance": maintenance_view,
        "System": system_view,
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
