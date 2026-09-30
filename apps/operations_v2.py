import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import asyncio
    import os
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime
    from pathlib import Path

    import marimo as mo

    from industrial_phm.application import (
        AcquisitionTelemetrySurface,
        AssetIdentity,
        ChannelSemanticBinding,
        CollectionDesiredState,
        FileSourceConfig,
        FileSourceMode,
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonPhaseUnbalanceRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        JsonWindowAnalysisRuntimeRepository,
        MeasurementDefinition,
        OpcUaSourceConfig,
        RegisteredSource,
        SourceLifecycleState,
        SourceType,
        SystemStateErrorEvidence,
        build_asset_detail,
        build_investigation_queue,
        build_maintenance_queue,
        build_operations_attention_queue,
        build_operations_monitor_view,
        build_operations_overview,
        build_setup_workspace,
        build_system_runtime_view,
        create_human_review_finding,
        discover_file_source,
        register_file_source,
        request_collection_state,
        transition_source_lifecycle,
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
    from industrial_phm.connectors import (
        OpcUaBrowseConfig,
        OpcUaNodeMapping,
        browse_opcua_variables,
    )
    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
    from industrial_phm.presentation import (
        OperationalAnalysisPresentationKind,
        operational_analysis_presentation_kind,
        operations_v2_theme_css,
        render_analysis_quality_markdown,
        render_monitor_assets_html,
        render_monitor_flow_html,
        render_setup_signals_html,
        render_setup_source_detail_html,
        render_setup_sources_html,
        render_system_diagnostics_html,
        render_system_errors_html,
        render_system_runtime_html,
        setup_workspace_css,
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
        SqliteCollectionControlRepository,
    )

    return (
        AcquisitionTelemetrySurface,
        AssetIdentity,
        ChannelSemanticBinding,
        CollectionDesiredState,
        DuckLakeAssetHistory,
        DuckLakeAssetHistoryConfig,
        FileSourceConfig,
        FileSourceMode,
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
        MeasurementDefinition,
        OpcUaBrowseConfig,
        OpcUaNodeMapping,
        OpcUaSourceConfig,
        OperationalAnalysisPresentationKind,
        Path,
        RegisteredSource,
        SourceLifecycleState,
        SourceType,
        SqliteAcquisitionSpool,
        SqliteAcquisitionSpoolConfig,
        SqliteAcquisitionTelemetryRepository,
        SqliteCollectionControlRepository,
        SystemStateErrorEvidence,
        ThreadPoolExecutor,
        UTC,
        asset_workspace_css,
        asyncio,
        browse_opcua_variables,
        build_asset_detail,
        build_asset_workspace_view,
        build_investigation_queue,
        build_maintenance_queue,
        build_operations_attention_queue,
        build_operations_monitor_view,
        build_operations_overview,
        build_setup_workspace,
        build_system_runtime_view,
        create_finding_review_event,
        create_human_review_finding,
        datetime,
        discover_file_source,
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
        register_file_source,
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
        render_setup_signals_html,
        render_setup_source_detail_html,
        render_setup_sources_html,
        render_system_diagnostics_html,
        render_system_errors_html,
        render_system_runtime_html,
        request_collection_state,
        resolve_measurement_range,
        setup_workspace_css,
        system_workspace_css,
        transition_source_lifecycle,
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
    SqliteCollectionControlRepository,
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
    collection_control_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_COLLECTION_CONTROL",
            "artifacts/operations/collection-control.sqlite",
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

    collection_records = ()
    if collection_control_path.is_file():
        try:
            collection_records = SqliteCollectionControlRepository(
                collection_control_path
            ).list_records()
        except (OSError, ValueError) as error:
            system_errors.append(
                SystemStateErrorEvidence(
                    "collection-control",
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

    system_diagnostics = (
        ("Source registry", str(registry_path)),
        ("Source runtime", str(source_runtime_path)),
        ("Acquisition telemetry", str(acquisition_telemetry_path)),
        ("Acquisition spool", str(acquisition_spool_path)),
        ("Collection control", str(collection_control_path)),
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
        collection_control_path,
        collection_records,
        finding_path,
        findings,
        history_assets,
        history_reader,
        lifecycle_records,
        monitor,
        overview,
        registered_sources,
        registry_path,
        review_events,
        review_path,
        system_diagnostics,
        system_errors,
    )


@app.cell
def _(OpcUaBrowseConfig, OpcUaNodeMapping, ThreadPoolExecutor, asyncio, browse_opcua_variables):
    def parse_opcua_mapping_lines(value: str):
        mappings = []
        for line_number, raw_line in enumerate(value.splitlines(), start=1):
            _line = raw_line.strip()
            if not _line:
                continue
            if "," not in _line:
                raise ValueError(
                    f"Mapping line {line_number} must use signal_id,node_id"
                )
            _channel_id, _node_id = _line.split(",", 1)
            mappings.append(
                OpcUaNodeMapping(
                    channel_id=_channel_id.strip(),
                    node_id=_node_id.strip(),
                )
            )
        return tuple(mappings)

    def run_setup_opcua_browse(*, endpoint_url: str, timeout_seconds: float):
        _config = OpcUaBrowseConfig(
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
        )

        def _run():
            return asyncio.run(browse_opcua_variables(_config))

        with ThreadPoolExecutor(max_workers=1) as _executor:
            return _executor.submit(_run).result()

    return parse_opcua_mapping_lines, run_setup_opcua_browse


@app.cell
def _(collection_records, lifecycle_records, mo, registered_sources):
    get_setup_sources, set_setup_sources = mo.state(tuple(registered_sources))
    get_setup_lifecycles, set_setup_lifecycles = mo.state(tuple(lifecycle_records))
    get_setup_collection, set_setup_collection = mo.state(tuple(collection_records))
    get_setup_error, set_setup_error = mo.state("")
    get_setup_success, set_setup_success = mo.state("")
    get_file_discovery, set_file_discovery = mo.state(None)
    get_file_discovery_signature, set_file_discovery_signature = mo.state(None)
    get_opcua_browse, set_opcua_browse = mo.state(None)
    get_opcua_browse_signature, set_opcua_browse_signature = mo.state(None)
    get_pending_semantics, set_pending_semantics = mo.state({})
    return (
        get_file_discovery,
        get_file_discovery_signature,
        get_opcua_browse,
        get_opcua_browse_signature,
        get_pending_semantics,
        get_setup_collection,
        get_setup_error,
        get_setup_lifecycles,
        get_setup_sources,
        get_setup_success,
        set_file_discovery,
        set_file_discovery_signature,
        set_opcua_browse,
        set_opcua_browse_signature,
        set_pending_semantics,
        set_setup_collection,
        set_setup_error,
        set_setup_lifecycles,
        set_setup_sources,
        set_setup_success,
    )


@app.cell
def _(
    collection_records,
    lifecycle_records,
    refresh_button,
    registered_sources,
    set_pending_semantics,
    set_setup_collection,
    set_setup_error,
    set_setup_lifecycles,
    set_setup_sources,
    set_setup_success,
):
    if refresh_button.value:
        set_setup_sources(tuple(registered_sources))
        set_setup_lifecycles(tuple(lifecycle_records))
        set_setup_collection(tuple(collection_records))
        set_pending_semantics({})
        set_setup_error("")
        set_setup_success("")
    return


@app.cell
def _(
    build_setup_workspace,
    get_setup_collection,
    get_setup_error,
    get_setup_lifecycles,
    get_setup_sources,
    get_setup_success,
):
    setup_sources = get_setup_sources()
    setup_lifecycles = get_setup_lifecycles()
    setup_collection = get_setup_collection()
    setup_error = get_setup_error()
    setup_success = get_setup_success()
    setup_workspace = build_setup_workspace(
        sources=setup_sources,
        lifecycle_records=setup_lifecycles,
        collection_records=setup_collection,
    )
    return (
        setup_collection,
        setup_error,
        setup_lifecycles,
        setup_sources,
        setup_success,
        setup_workspace,
    )


@app.cell
def _():
    setup_selection = {"source_id": None}
    return (setup_selection,)


@app.cell
def _(mo, setup_selection, setup_workspace):
    _setup_source_ids = tuple(item.source_id for item in setup_workspace.sources)
    if _setup_source_ids:
        _selected_source_id = (
            setup_selection["source_id"]
            if setup_selection["source_id"] in _setup_source_ids
            else _setup_source_ids[0]
        )
        setup_source_selector = mo.ui.dropdown(
            options=list(_setup_source_ids),
            value=_selected_source_id,
            label="Data source",
            full_width=True,
            on_change=lambda value: setup_selection.update(source_id=value),
        )
        setup_selected_source = next(
            item for item in setup_workspace.sources if item.source_id == _selected_source_id
        )
    else:
        setup_source_selector = None
        setup_selected_source = None
    setup_section = mo.ui.radio(
        options=[
            "Data Sources",
            "Signal Mapping",
            "Measurement Semantics",
            "Analysis Configuration",
        ],
        value="Data Sources",
        label="Setup area",
    )
    return setup_section, setup_selected_source, setup_source_selector


@app.cell
def _(SourceLifecycleState, mo, setup_selected_source):
    setup_enable_button = None
    setup_pause_button = None
    if setup_selected_source is not None:
        if setup_selected_source.lifecycle_state == SourceLifecycleState.ACTIVE:
            setup_pause_button = mo.ui.run_button(label="Pause source")
        else:
            setup_enable_button = mo.ui.run_button(label="Enable source", kind="success")
    return setup_enable_button, setup_pause_button


@app.cell
def _(CollectionDesiredState, SourceType, mo, setup_selected_source):
    setup_start_collection_button = None
    setup_stop_collection_button = None
    if (
        setup_selected_source is not None
        and setup_selected_source.source_type == SourceType.OPCUA
    ):
        if setup_selected_source.collection_desired_state == CollectionDesiredState.RUNNING:
            setup_stop_collection_button = mo.ui.run_button(label="Stop collection")
        else:
            setup_start_collection_button = mo.ui.run_button(
                label="Start collection",
                kind="success",
            )
    return setup_start_collection_button, setup_stop_collection_button


@app.cell
def _(
    JsonSourceRepository,
    SourceLifecycleState,
    datetime,
    registry_path,
    set_setup_error,
    set_setup_lifecycles,
    set_setup_success,
    setup_enable_button,
    setup_pause_button,
    setup_selected_source,
    transition_source_lifecycle,
):
    _setup_lifecycle_target = None
    if setup_enable_button is not None and setup_enable_button.value:
        _setup_lifecycle_target = SourceLifecycleState.ACTIVE
    elif setup_pause_button is not None and setup_pause_button.value:
        _setup_lifecycle_target = SourceLifecycleState.PAUSED

    if _setup_lifecycle_target is not None:
        try:
            if setup_selected_source is None:
                raise ValueError("select a data source before changing its use state")
            _repository = JsonSourceRepository(registry_path)
            _record = transition_source_lifecycle(
                _repository,
                setup_selected_source.source_id,
                _setup_lifecycle_target,
                changed_at=datetime.now().astimezone(),
            )
            _sources = _repository.list_sources()
            _lifecycles = tuple(
                _repository.get_lifecycle(item.source_id) for item in _sources
            )
        except (LookupError, OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            set_setup_lifecycles(_lifecycles)
            set_setup_error("")
            set_setup_success(
                f"Source use changed: {_record.source_id} → {_record.state.value}."
            )
    return


@app.cell
def _(
    CollectionDesiredState,
    JsonSourceRepository,
    SqliteCollectionControlRepository,
    collection_control_path,
    datetime,
    registry_path,
    request_collection_state,
    set_setup_collection,
    set_setup_error,
    set_setup_success,
    setup_selected_source,
    setup_start_collection_button,
    setup_stop_collection_button,
):
    _setup_collection_target = None
    if setup_start_collection_button is not None and setup_start_collection_button.value:
        _setup_collection_target = CollectionDesiredState.RUNNING
    elif setup_stop_collection_button is not None and setup_stop_collection_button.value:
        _setup_collection_target = CollectionDesiredState.STOPPED

    if _setup_collection_target is not None:
        try:
            if setup_selected_source is None:
                raise ValueError("select an OPC UA source before changing collection")
            _source_repository = JsonSourceRepository(registry_path)
            _control_repository = SqliteCollectionControlRepository(
                collection_control_path
            )
            _record = request_collection_state(
                _source_repository,
                _source_repository,
                _control_repository,
                setup_selected_source.source_id,
                _setup_collection_target,
                requested_at=datetime.now().astimezone(),
            )
            _records = _control_repository.list_records()
        except (LookupError, OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            set_setup_collection(_records)
            set_setup_error("")
            set_setup_success(
                "Collection request saved: "
                f"{_record.source_id} → {_record.desired_state.value}. "
                "The browser does not start or supervise the collector process."
            )
    return


@app.cell
def _(SourceType, mo):
    add_source_type = mo.ui.radio(
        options=["File", "OPC UA"],
        value="OPC UA",
        label="Source type",
    )
    add_source_id = mo.ui.text(label="Source ID", full_width=True)
    add_source_name = mo.ui.text(label="Name", full_width=True)
    add_asset_id = mo.ui.text(label="Asset", full_width=True)
    add_point_id = mo.ui.text(label="Measurement point (optional)", full_width=True)

    file_path_input = mo.ui.text(
        label="File or directory path",
        full_width=True,
    )
    file_mode_input = mo.ui.radio(
        options=["Snapshot", "History directory"],
        value="Snapshot",
        label="File shape",
    )
    file_discover_button = mo.ui.run_button(label="Discover file")
    file_timestamp_input = mo.ui.text(
        value="timestamp",
        label="Timestamp column (optional for snapshot)",
        full_width=True,
    )
    file_sampling_rate_input = mo.ui.text(
        value="",
        label="Sampling rate Hz (optional)",
        full_width=True,
    )

    opcua_endpoint_input = mo.ui.text(
        label="Endpoint",
        placeholder="opc.tcp://host:4840",
        full_width=True,
    )
    opcua_timeout_input = mo.ui.text(value="4", label="Timeout seconds")
    opcua_browse_button = mo.ui.run_button(label="Connect & browse signals")
    opcua_explicit_mapping_input = mo.ui.text_area(
        value="",
        label="Advanced explicit mapping (signal_id,node_id)",
        rows=4,
        full_width=True,
    )
    return (
        add_asset_id,
        add_point_id,
        add_source_id,
        add_source_name,
        add_source_type,
        file_discover_button,
        file_mode_input,
        file_path_input,
        file_sampling_rate_input,
        file_timestamp_input,
        opcua_browse_button,
        opcua_endpoint_input,
        opcua_explicit_mapping_input,
        opcua_timeout_input,
    )


@app.cell
def _(
    FileSourceMode,
    Path,
    discover_file_source,
    file_discover_button,
    file_mode_input,
    file_path_input,
    set_file_discovery,
    set_file_discovery_signature,
    set_setup_error,
    set_setup_success,
):
    if file_discover_button.value:
        _mode = (
            FileSourceMode.SNAPSHOT
            if file_mode_input.value == "Snapshot"
            else FileSourceMode.HISTORY_DIRECTORY
        )
        _path = file_path_input.value.strip()
        try:
            _discovery = discover_file_source(Path(_path), _mode)
        except (OSError, ValueError) as error:
            set_file_discovery(None)
            set_file_discovery_signature(None)
            set_setup_success("")
            set_setup_error(str(error))
        else:
            set_file_discovery(_discovery)
            set_file_discovery_signature((file_mode_input.value, _path))
            set_setup_error("")
            set_setup_success("File discovery completed. Select the signals to keep.")
    return


@app.cell
def _(
    get_file_discovery,
    get_file_discovery_signature,
    file_mode_input,
    file_path_input,
    mo,
):
    file_discovery = get_file_discovery()
    file_discovery_signature = get_file_discovery_signature()
    _file_signature = (file_mode_input.value, file_path_input.value.strip())
    file_discovery_current = (
        file_discovery is not None and file_discovery_signature == _file_signature
    )
    if file_discovery_current:
        file_signal_selection = mo.ui.multiselect(
            options=list(file_discovery.common_columns),
            value=[],
            label="Signals to keep",
            full_width=True,
        )
    else:
        file_signal_selection = None
    return file_discovery, file_discovery_current, file_signal_selection


@app.cell
def _(
    opcua_browse_button,
    opcua_endpoint_input,
    opcua_timeout_input,
    run_setup_opcua_browse,
    set_opcua_browse,
    set_opcua_browse_signature,
    set_setup_error,
    set_setup_success,
):
    if opcua_browse_button.value:
        _endpoint = opcua_endpoint_input.value.strip()
        _timeout = opcua_timeout_input.value.strip()
        try:
            _result = run_setup_opcua_browse(
                endpoint_url=_endpoint,
                timeout_seconds=float(_timeout),
            )
        except Exception as error:
            set_opcua_browse(None)
            set_opcua_browse_signature(None)
            set_setup_success("")
            set_setup_error(str(error))
        else:
            set_opcua_browse(_result)
            set_opcua_browse_signature((_endpoint, _timeout))
            set_setup_error("")
            set_setup_success(
                "Browse completed. This bounded session discovered signal identity only."
            )
    return


@app.cell
def _(
    get_opcua_browse,
    get_opcua_browse_signature,
    mo,
    opcua_endpoint_input,
    opcua_timeout_input,
):
    opcua_browse = get_opcua_browse()
    opcua_browse_signature = get_opcua_browse_signature()
    _opcua_signature = (
        opcua_endpoint_input.value.strip(),
        opcua_timeout_input.value.strip(),
    )
    opcua_browse_current = (
        opcua_browse is not None and opcua_browse_signature == _opcua_signature
    )
    if opcua_browse_current:
        opcua_browse_by_label = {
            " / ".join(item.browse_path) + f" · {item.node_id}": item
            for item in opcua_browse.variables
        }
        opcua_signal_selection = mo.ui.multiselect(
            options=list(opcua_browse_by_label),
            value=[],
            label="Signals to keep",
            full_width=True,
        )
    else:
        opcua_browse_by_label = {}
        opcua_signal_selection = None
    return opcua_browse_by_label, opcua_browse_current, opcua_signal_selection


@app.cell
def _(
    OpcUaNodeMapping,
    opcua_browse_by_label,
    opcua_browse_current,
    opcua_explicit_mapping_input,
    opcua_signal_selection,
    parse_opcua_mapping_lines,
):
    _browse_mappings = tuple(
        OpcUaNodeMapping(
            channel_id=opcua_browse_by_label[label].browse_name,
            node_id=opcua_browse_by_label[label].node_id,
        )
        for label in (() if opcua_signal_selection is None else opcua_signal_selection.value)
    )
    try:
        _explicit_mappings = parse_opcua_mapping_lines(opcua_explicit_mapping_input.value)
        opcua_mapping_error = ""
    except ValueError as error:
        _explicit_mappings = ()
        opcua_mapping_error = str(error)
    opcua_candidate_mappings = (
        _browse_mappings if opcua_browse_current and _browse_mappings else _explicit_mappings
    )
    return opcua_candidate_mappings, opcua_mapping_error


@app.cell
def _(mo, opcua_candidate_mappings):
    _semantic_channels = [item.channel_id for item in opcua_candidate_mappings]
    if _semantic_channels:
        semantic_channel_input = mo.ui.dropdown(
            options=_semantic_channels,
            value=_semantic_channels[0],
            label="Signal",
            full_width=True,
        )
        semantic_observed_property_input = mo.ui.text(
            label="Observed property",
            full_width=True,
        )
        semantic_scope_input = mo.ui.text(label="Scope (optional)", full_width=True)
        semantic_statistic_input = mo.ui.text(
            label="Statistic (optional)",
            full_width=True,
        )
        semantic_unit_input = mo.ui.text(label="Unit (optional)", full_width=True)
        semantic_unit_evidence_input = mo.ui.text(
            label="Unit evidence (required when unit is known)",
            full_width=True,
        )
        semantic_version_input = mo.ui.text(label="Semantic version", full_width=True)
        semantic_evidence_input = mo.ui.text(
            label="Interpretation evidence",
            full_width=True,
        )
        semantic_save_button = mo.ui.run_button(label="Add / update meaning")
        semantic_clear_button = mo.ui.run_button(label="Keep unresolved")
    else:
        semantic_channel_input = None
        semantic_observed_property_input = None
        semantic_scope_input = None
        semantic_statistic_input = None
        semantic_unit_input = None
        semantic_unit_evidence_input = None
        semantic_version_input = None
        semantic_evidence_input = None
        semantic_save_button = None
        semantic_clear_button = None
    return (
        semantic_channel_input,
        semantic_clear_button,
        semantic_evidence_input,
        semantic_observed_property_input,
        semantic_save_button,
        semantic_scope_input,
        semantic_statistic_input,
        semantic_unit_evidence_input,
        semantic_unit_input,
        semantic_version_input,
    )


@app.cell
def _(
    ChannelSemanticBinding,
    MeasurementDefinition,
    add_source_id,
    get_pending_semantics,
    semantic_channel_input,
    semantic_clear_button,
    semantic_evidence_input,
    semantic_observed_property_input,
    semantic_save_button,
    semantic_scope_input,
    semantic_statistic_input,
    semantic_unit_evidence_input,
    semantic_unit_input,
    semantic_version_input,
    set_pending_semantics,
    set_setup_error,
    set_setup_success,
):
    if semantic_save_button is not None and semantic_save_button.value:
        try:
            if semantic_channel_input is None:
                raise ValueError("select a mapped signal before defining meaning")
            _source_id = add_source_id.value.strip()
            _channel_id = semantic_channel_input.value
            _binding = ChannelSemanticBinding(
                source_id=_source_id,
                channel_id=_channel_id,
                version=semantic_version_input.value.strip(),
                definition=MeasurementDefinition(
                    observed_property=semantic_observed_property_input.value.strip() or None,
                    scope=semantic_scope_input.value.strip() or None,
                    statistic=semantic_statistic_input.value.strip() or None,
                    unit=semantic_unit_input.value.strip() or None,
                    unit_evidence=semantic_unit_evidence_input.value.strip() or None,
                ),
                interpretation_evidence=semantic_evidence_input.value.strip(),
            )
        except ValueError as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            _current = dict(get_pending_semantics())
            _current[_channel_id] = _binding
            set_pending_semantics(_current)
            set_setup_error("")
            set_setup_success(f"Meaning saved for {_channel_id}.")
    elif semantic_clear_button is not None and semantic_clear_button.value:
        if semantic_channel_input is not None:
            _current = dict(get_pending_semantics())
            _current.pop(semantic_channel_input.value, None)
            set_pending_semantics(_current)
            set_setup_error("")
            set_setup_success(
                f"{semantic_channel_input.value} will remain unresolved."
            )
    return


@app.cell
def _(get_pending_semantics):
    pending_semantics = get_pending_semantics()
    return (pending_semantics,)


@app.cell
def _(mo):
    register_setup_source_button = mo.ui.run_button(
        label="Review & save source",
        kind="success",
    )
    return (register_setup_source_button,)


@app.cell
def _(
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    datetime,
    file_discovery,
    file_discovery_current,
    file_mode_input,
    file_path_input,
    file_sampling_rate_input,
    file_signal_selection,
    file_timestamp_input,
    opcua_candidate_mappings,
    opcua_endpoint_input,
    opcua_mapping_error,
    opcua_timeout_input,
    pending_semantics,
    register_file_source,
    register_setup_source_button,
    registry_path,
    set_pending_semantics,
    set_setup_error,
    set_setup_lifecycles,
    set_setup_sources,
    set_setup_success,
    add_asset_id,
    add_point_id,
    add_source_id,
    add_source_name,
    add_source_type,
):
    if register_setup_source_button.value:
        try:
            _source_id = add_source_id.value.strip()
            _candidate = None
            _repository = JsonSourceRepository(registry_path)
            if add_source_type.value == "File":
                if not file_discovery_current or file_discovery is None:
                    raise ValueError("discover the file source before saving")
                _signals = tuple(
                    () if file_signal_selection is None else file_signal_selection.value
                )
                if not _signals:
                    raise ValueError("select at least one file signal")
                _common = set(file_discovery.common_columns)
                _timestamp = file_timestamp_input.value.strip() or None
                if _timestamp is not None and _timestamp not in _common:
                    raise ValueError(
                        "timestamp column was not discovered in every CSV file"
                    )
                _rate_text = file_sampling_rate_input.value.strip()
                _candidate = RegisteredSource(
                    source_id=_source_id,
                    name=add_source_name.value.strip(),
                    config=FileSourceConfig(
                        source_path=file_path_input.value.strip(),
                        asset_id=add_asset_id.value.strip(),
                        measurement_point_id=add_point_id.value.strip() or None,
                        channel_columns=_signals,
                        mode=(
                            FileSourceMode.SNAPSHOT
                            if file_mode_input.value == "Snapshot"
                            else FileSourceMode.HISTORY_DIRECTORY
                        ),
                        timestamp_column=_timestamp,
                        sampling_rate_hz=None if not _rate_text else float(_rate_text),
                    ),
                    registered_at=datetime.now().astimezone(),
                )
                register_file_source(_candidate, _repository)
            else:
                if opcua_mapping_error:
                    raise ValueError(opcua_mapping_error)
                if not opcua_candidate_mappings:
                    raise ValueError(
                        "connect and select signals, or provide explicit advanced mapping"
                    )
                _binding_by_channel = {
                    channel: binding
                    for channel, binding in pending_semantics.items()
                    if channel in {item.channel_id for item in opcua_candidate_mappings}
                }
                _candidate = RegisteredSource(
                    source_id=_source_id,
                    name=add_source_name.value.strip(),
                    config=OpcUaSourceConfig(
                        endpoint_url=opcua_endpoint_input.value.strip(),
                        asset_id=add_asset_id.value.strip(),
                        measurement_point_id=add_point_id.value.strip() or None,
                        node_mappings=opcua_candidate_mappings,
                        timeout_seconds=float(opcua_timeout_input.value.strip()),
                        semantic_bindings=tuple(
                            _binding_by_channel[channel]
                            for channel in sorted(_binding_by_channel)
                        ),
                    ),
                    registered_at=datetime.now().astimezone(),
                )
                _repository.register(_candidate)

            _sources = _repository.list_sources()
            _lifecycles = tuple(
                _repository.get_lifecycle(item.source_id) for item in _sources
            )
        except (OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            set_setup_sources(_sources)
            set_setup_lifecycles(_lifecycles)
            set_pending_semantics({})
            set_setup_error("")
            set_setup_success(
                f"Source saved: {_candidate.source_id}. Enable it when ready to use."
            )
    return


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
    add_asset_id,
    add_point_id,
    add_source_id,
    add_source_name,
    add_source_type,
    file_discover_button,
    file_discovery,
    file_discovery_current,
    file_mode_input,
    file_path_input,
    file_sampling_rate_input,
    file_signal_selection,
    file_timestamp_input,
    mo,
    opcua_browse,
    opcua_browse_button,
    opcua_browse_current,
    opcua_candidate_mappings,
    opcua_endpoint_input,
    opcua_explicit_mapping_input,
    opcua_mapping_error,
    opcua_signal_selection,
    opcua_timeout_input,
    pending_semantics,
    register_setup_source_button,
    render_setup_signals_html,
    render_setup_source_detail_html,
    render_setup_sources_html,
    semantic_channel_input,
    semantic_clear_button,
    semantic_evidence_input,
    semantic_observed_property_input,
    semantic_save_button,
    semantic_scope_input,
    semantic_statistic_input,
    semantic_unit_evidence_input,
    semantic_unit_input,
    semantic_version_input,
    setup_enable_button,
    setup_error,
    setup_pause_button,
    setup_section,
    setup_selected_source,
    setup_source_selector,
    setup_start_collection_button,
    setup_stop_collection_button,
    setup_success,
    setup_workspace,
):
    _message_blocks = []
    if setup_error:
        _message_blocks.append(
            mo.callout(setup_error, kind="danger", title="Setup action failed")
        )
    if setup_success:
        _message_blocks.append(
            mo.callout(setup_success, kind="success", title="Setup updated")
        )

    if setup_selected_source is None:
        _selected_source_panel = mo.md(
            "### Selected source\n\nNo data source is configured yet."
        )
    else:
        _source_actions = [
            button
            for button in (
                setup_enable_button,
                setup_pause_button,
                setup_start_collection_button,
                setup_stop_collection_button,
            )
            if button is not None
        ]
        _selected_source_panel = mo.vstack(
            [
                setup_source_selector,
                mo.Html(render_setup_source_detail_html(setup_selected_source)),
                mo.hstack(_source_actions, justify="start", gap=0.6),
                mo.md(
                    "Enable/Pause changes whether a runtime may use the source. "
                    "Start/Stop collection writes desired collection state for OPC UA; "
                    "it does not prove the collector process is running or connected."
                ),
            ],
            gap=0.8,
        )

    if add_source_type.value == "File":
        if file_discovery_current and file_discovery is not None:
            _preview_rows = [
                dict(zip(file_discovery.representative_columns, row, strict=True))
                for row in file_discovery.preview_rows
            ]
            _file_discovery_view = mo.vstack(
                [
                    mo.md(
                        f"Discovered **{file_discovery.file_count}** file(s), "
                        f"**{len(file_discovery.common_columns)}** common column(s)."
                    ),
                    mo.ui.table(_preview_rows, selection=None),
                    file_signal_selection,
                ],
                gap=0.6,
            )
        else:
            _file_discovery_view = mo.md(
                "Run discovery after choosing a file or history directory. "
                "No column meaning is inferred during discovery."
            )

        _source_wizard = mo.vstack(
            [
                mo.md("### Add data source"),
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">1 · Source</div>'
                    '<div class="phm-setup-help">Choose the prepared file boundary and declare asset identity.</div>'
                    "</div>"
                ),
                add_source_type,
                mo.hstack([add_source_id, add_source_name], widths="equal"),
                mo.hstack([add_asset_id, add_point_id], widths="equal"),
                file_mode_input,
                file_path_input,
                file_discover_button,
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">2 · Select signals</div>'
                    '<div class="phm-setup-help">Keep only discovered columns that belong to this source mapping.</div>'
                    "</div>"
                ),
                _file_discovery_view,
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">3 · Define time & sampling</div>'
                    '<div class="phm-setup-help">FILE registration currently preserves column identity; it does not infer physical measurement semantics.</div>'
                    "</div>"
                ),
                mo.hstack(
                    [file_timestamp_input, file_sampling_rate_input],
                    widths="equal",
                ),
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">4 · Review & save</div>'
                    '<div class="phm-setup-help">The file is validated before its registration is persisted.</div>'
                    "</div>"
                ),
                register_setup_source_button,
            ],
            gap=0.75,
        )
    else:
        if opcua_browse_current and opcua_browse is not None:
            _browse_status = mo.md(
                f"Browse completed: **{len(opcua_browse.variables)}** variable candidate(s), "
                f"visited **{opcua_browse.visited_node_count}** node(s)"
                + (" · result truncated" if opcua_browse.truncated else "")
                + "."
            )
        else:
            _browse_status = mo.md(
                "Connect & browse uses one bounded anonymous session to discover variable identity. "
                "It does not read signal values or prove ongoing connection health."
            )

        if opcua_mapping_error:
            _mapping_view = mo.callout(
                opcua_mapping_error,
                kind="danger",
                title="Explicit mapping invalid",
            )
        elif opcua_candidate_mappings:
            _mapping_view = mo.ui.table(
                [
                    {"Signal": item.channel_id, "NodeId": item.node_id}
                    for item in opcua_candidate_mappings
                ],
                selection=None,
            )
        else:
            _mapping_view = mo.md("No signal mapping selected yet.")

        _semantic_rows = [
            {
                "Signal": channel_id,
                "Observed property": binding.definition.observed_property or "Unresolved",
                "Scope": binding.definition.scope or "—",
                "Statistic": binding.definition.statistic or "—",
                "Unit": binding.definition.unit or "—",
                "Version": binding.version,
                "Evidence": binding.interpretation_evidence,
            }
            for channel_id, binding in sorted(pending_semantics.items())
        ]
        _semantic_editor = (
            mo.vstack(
                [
                    semantic_channel_input,
                    mo.hstack(
                        [semantic_observed_property_input, semantic_scope_input],
                        widths="equal",
                    ),
                    mo.hstack(
                        [semantic_statistic_input, semantic_unit_input],
                        widths="equal",
                    ),
                    semantic_unit_evidence_input,
                    mo.hstack(
                        [semantic_version_input, semantic_evidence_input],
                        widths="equal",
                    ),
                    mo.hstack(
                        [semantic_save_button, semantic_clear_button],
                        justify="start",
                        gap=0.6,
                    ),
                    (
                        mo.ui.table(_semantic_rows, selection=None)
                        if _semantic_rows
                        else mo.md(
                            "No explicit measurement meaning has been added. "
                            "Unmapped meaning remains **Unresolved**."
                        )
                    ),
                ],
                gap=0.6,
            )
            if semantic_channel_input is not None
            else mo.md("Select at least one mapped signal before defining meaning.")
        )

        _source_wizard = mo.vstack(
            [
                mo.md("### Add data source"),
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">1 · Connect</div>'
                    '<div class="phm-setup-help">Declare endpoint and asset identity, then run a bounded browse.</div>'
                    "</div>"
                ),
                add_source_type,
                mo.hstack([add_source_id, add_source_name], widths="equal"),
                mo.hstack([add_asset_id, add_point_id], widths="equal"),
                mo.hstack([opcua_endpoint_input, opcua_timeout_input], widths=[0.75, 0.25]),
                opcua_browse_button,
                _browse_status,
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">2 · Select signals</div>'
                    '<div class="phm-setup-help">Browse selection defines explicit NodeId mapping. NodeId and BrowseName do not establish physical meaning.</div>'
                    "</div>"
                ),
                (
                    opcua_signal_selection
                    if opcua_signal_selection is not None
                    else mo.md("No current browse result.")
                ),
                _mapping_view,
                mo.accordion(
                    {"Advanced explicit NodeId mapping": opcua_explicit_mapping_input}
                ),
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">3 · Define meaning</div>'
                    '<div class="phm-setup-help">Meaning is explicit, versioned, and evidence-backed. Leave channels unresolved when meaning is not established.</div>'
                    "</div>"
                ),
                _semantic_editor,
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">4 · Review & save</div>'
                    '<div class="phm-setup-help">Saving registers configuration only. It does not enable the source or start collection.</div>'
                    "</div>"
                ),
                register_setup_source_button,
            ],
            gap=0.75,
        )

    _data_sources_view = mo.vstack(
        [
            mo.Html(render_setup_sources_html(setup_workspace)),
            _selected_source_panel,
            mo.accordion({"Add data source": _source_wizard}),
        ],
        gap=1.0,
    )

    if setup_selected_source is None:
        _signal_mapping_view = mo.md(
            "## Signal Mapping\n\nSelect or add a data source first."
        )
        _semantics_view = mo.md(
            "## Measurement Semantics\n\nSelect or add a data source first."
        )
    else:
        _signal_mapping_view = mo.vstack(
            [
                setup_source_selector,
                mo.Html(render_setup_signals_html(setup_selected_source)),
                mo.md(
                    "Signal identity comes from declared FILE columns or explicit OPC UA NodeId mapping. "
                    "This page does not infer component hierarchy or physical meaning from names."
                ),
            ],
            gap=0.8,
        )
        _defined, _total = setup_selected_source.semantic_coverage
        _semantics_view = mo.vstack(
            [
                setup_source_selector,
                mo.md(
                    f"### Measurement Semantics\n\n"
                    f"Explicit meaning coverage: **{_defined} / {_total}** signal(s)."
                ),
                mo.Html(render_setup_signals_html(setup_selected_source)),
                mo.md(
                    "Existing registrations are immutable evidence in the current registry contract. "
                    "Measurement meaning is defined during registration; unresolved channels stay unresolved "
                    "instead of being inferred from signal names."
                ),
            ],
            gap=0.8,
        )

    _analysis_configuration_view = mo.vstack(
        [
            mo.md(
                "## Analysis Configuration\n\n"
                "Operational analysis policies are versioned outside this Setup workspace today. "
                "The live three-phase runner and FILE analysis preserve their policy/version in evidence; "
                "this screen does not expose controls that the application contract cannot persist safely."
            ),
            mo.md(
                "Use **System** to verify analysis-service runtime status and **Investigations** "
                "to inspect the exact policy/evidence of completed analyses."
            ),
        ],
        gap=0.8,
    )

    _setup_sections = {
        "Data Sources": _data_sources_view,
        "Signal Mapping": _signal_mapping_view,
        "Measurement Semantics": _semantics_view,
        "Analysis Configuration": _analysis_configuration_view,
    }
    setup_view = mo.vstack(
        [
            mo.hstack(
                [
                    mo.md(
                        "## Setup\n\n"
                        "Connect data sources, map signals, and record explicit measurement meaning."
                    ),
                    setup_section,
                ],
                widths=[0.42, 0.58],
                align="start",
            ),
            *_message_blocks,
            _setup_sections[setup_section.value],
        ],
        gap=1.0,
    )
    return (setup_view,)


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
