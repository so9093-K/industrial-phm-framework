import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    from datetime import UTC, datetime
    from pathlib import Path

    import marimo as mo

    from industrial_phm.application import (
        FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID,
        AssetIdentity,
        ChannelSemanticBinding,
        CollectionDesiredState,
        FileSourceConfig,
        FileSourceMode,
        MeasurementDefinition,
        OpcUaSourceConfig,
        RegisteredSource,
        SourceLifecycleState,
        SourceRuntimeCycleState,
        SourceType,
        build_asset_detail,
        build_investigation_queue,
        build_maintenance_queue,
        build_setup_workspace,
        build_system_runtime_view,
        discover_file_source,
    )
    from industrial_phm.application.asset_display import resolve_asset_display_names
    from industrial_phm.application.maintenance_review import (
        FindingReviewAction,
        FindingReviewStatus,
    )
    from industrial_phm.application.measurement_history import resolve_measurement_range
    from industrial_phm.application.operations_assets import build_asset_workspace_view
    from industrial_phm.application.operations_investigations import (
        InvestigationReviewState,
    )
    from industrial_phm.connectors import OpcUaNodeMapping
    from industrial_phm.presentation import (
        OPERATIONS_PAGE_OPTIONS,
        OperationalAnalysisPresentationKind,
        initial_operations_page,
        monitor_attention_category,
        monitor_context_attention,
        monitor_signal_channels,
        operational_analysis_presentation_kind,
        operations_theme_css,
        render_analysis_quality_markdown,
        render_monitor_asset_context_html,
        render_monitor_signal_overview_html,
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
        render_multi_signal_measurement_aggregation_svg,
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
        investigation_group_option_label,
        investigation_queue_option_label,
        investigation_review_label,
        investigation_workspace_css,
        render_investigation_evidence_identity_html,
        render_investigation_summary_html,
    )
    from industrial_phm.presentation.operations_live import (
        initial_signal_channel,
        live_observation_css,
        live_observation_recent_page,
        render_live_observation_html,
    )
    from industrial_phm.presentation.operations_maintenance import (
        maintenance_queue_label,
        maintenance_status_label,
        maintenance_workspace_css,
        render_maintenance_evidence_html,
        render_maintenance_identity_html,
        render_maintenance_summary_html,
        render_maintenance_timeline_html,
    )
    from industrial_phm.presentation.operations_navigation import (
        resolve_finding_investigation_route,
        resolve_investigation_route,
        resolve_operations_attention_route,
    )
    from industrial_phm.presentation.phase_unbalance import (
        phase_unbalance_exclusion_rows,
        phase_unbalance_provenance_rows,
        phase_unbalance_summary_rows,
        render_phase_unbalance_svg,
    )
    from industrial_phm.runtime.operations_app_actions import (
        OperationsActionError,
        OperationsDiagnosticKind,
    )
    from industrial_phm.runtime.operations_app_composition import project_review_workflow
    from industrial_phm.runtime.operations_app_context import load_operations_app_context
    from industrial_phm.runtime.operations_live import (
        OperationsReadError,
        list_operations_history_channels,
        load_operations_live_observation,
        query_operations_latest_asset_measurements,
        query_operations_latest_measurements,
        query_operations_measurement_aggregation,
        query_operations_measurement_page,
        query_operations_multi_signal_measurement_aggregation,
    )

    return (
        AssetIdentity,
        ChannelSemanticBinding,
        CollectionDesiredState,
        FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID,
        FileSourceConfig,
        FileSourceMode,
        FindingReviewAction,
        FindingReviewStatus,
        InvestigationReviewState,
        MeasurementDefinition,
        OpcUaNodeMapping,
        OpcUaSourceConfig,
        OPERATIONS_PAGE_OPTIONS,
        OperationalAnalysisPresentationKind,
        OperationsActionError,
        OperationsDiagnosticKind,
        OperationsReadError,
        Path,
        RegisteredSource,
        SourceLifecycleState,
        SourceRuntimeCycleState,
        SourceType,
        UTC,
        asset_workspace_css,
        build_asset_detail,
        build_asset_workspace_view,
        build_investigation_queue,
        build_maintenance_queue,
        build_setup_workspace,
        build_system_runtime_view,
        datetime,
        discover_file_source,
        investigation_capability_label,
        investigation_group_option_label,
        investigation_queue_option_label,
        investigation_review_label,
        initial_operations_page,
        initial_signal_channel,
        investigation_workspace_css,
        latest_measurement_rows,
        live_observation_css,
        live_observation_recent_page,
        list_operations_history_channels,
        load_operations_app_context,
        load_operations_live_observation,
        maintenance_queue_label,
        maintenance_status_label,
        maintenance_workspace_css,
        measurement_aggregation_rows,
        measurement_aggregation_summary,
        measurement_history_range_summary,
        measurement_history_rows,
        mo,
        monitor_attention_category,
        monitor_context_attention,
        monitor_signal_channels,
        operational_analysis_presentation_kind,
        operations_theme_css,
        phase_unbalance_exclusion_rows,
        phase_unbalance_provenance_rows,
        phase_unbalance_summary_rows,
        query_operations_latest_asset_measurements,
        query_operations_latest_measurements,
        query_operations_multi_signal_measurement_aggregation,
        query_operations_measurement_aggregation,
        query_operations_measurement_page,
        render_analysis_quality_markdown,
        render_asset_analysis_html,
        render_asset_events_html,
        render_asset_header_html,
        render_asset_maintenance_html,
        render_asset_overview_html,
        render_investigation_evidence_identity_html,
        render_investigation_summary_html,
        render_live_observation_html,
        project_review_workflow,
        resolve_asset_display_names,
        resolve_finding_investigation_route,
        resolve_investigation_route,
        resolve_operations_attention_route,
        render_maintenance_evidence_html,
        render_maintenance_identity_html,
        render_maintenance_summary_html,
        render_maintenance_timeline_html,
        render_measurement_aggregation_svg,
        render_measurement_history_svg,
        render_multi_signal_measurement_aggregation_svg,
        render_monitor_asset_context_html,
        render_monitor_signal_overview_html,
        render_phase_unbalance_svg,
        render_setup_signals_html,
        render_setup_source_detail_html,
        render_setup_sources_html,
        render_system_diagnostics_html,
        render_system_errors_html,
        render_system_runtime_html,
        resolve_measurement_range,
        setup_workspace_css,
        system_workspace_css,
    )


@app.cell
def _(mo):
    refresh_button = mo.ui.run_button(label="Refresh")
    get_navigation_page, set_navigation_page = mo.state(None)
    return get_navigation_page, refresh_button, set_navigation_page


@app.cell
def _(load_operations_app_context, refresh_button):
    _refresh = refresh_button.value
    del _refresh

    operations_context = load_operations_app_context()
    _snapshot = operations_context.snapshot
    operations_actions = operations_context.actions

    assessed_at = _snapshot.assessed_at
    registered_sources = _snapshot.registered_sources
    lifecycle_records = _snapshot.lifecycle_records
    freshness_policies = _snapshot.freshness_policies
    analysis_results = _snapshot.analysis_results
    findings = _snapshot.findings
    review_events = _snapshot.review_events
    acquisition_surfaces = _snapshot.acquisition_surfaces
    collection_service = _snapshot.collection_service
    analysis_runtime = _snapshot.analysis_runtime
    history_reader = _snapshot.history_reader
    history_assets = _snapshot.history_assets
    collection_records = _snapshot.collection_records
    skipped_analysis_attempts = _snapshot.skipped_analysis_attempts
    live_flow_timing = _snapshot.live_flow_timing
    system_diagnostics = _snapshot.system_diagnostics
    system_errors = _snapshot.system_errors

    return (
        acquisition_surfaces,
        analysis_results,
        analysis_runtime,
        assessed_at,
        collection_service,
        collection_records,
        findings,
        freshness_policies,
        history_assets,
        history_reader,
        lifecycle_records,
        live_flow_timing,
        operations_actions,
        operations_context,
        registered_sources,
        review_events,
        skipped_analysis_attempts,
        system_diagnostics,
        system_errors,
    )


@app.cell
def _(registered_sources, resolve_asset_display_names):
    # Presentation labels only; asset_id stays the identity for every lookup.
    asset_names = resolve_asset_display_names(registered_sources)
    return (asset_names,)


@app.cell
def _(
    get_navigation_page,
    initial_operations_page,
    registered_sources,
    set_navigation_page,
):
    navigation_initial_page = get_navigation_page()
    if navigation_initial_page is None:
        navigation_initial_page = initial_operations_page(
            has_registered_sources=bool(registered_sources)
        )
        set_navigation_page(navigation_initial_page)
    return (navigation_initial_page,)


@app.cell
def _(
    OPERATIONS_PAGE_OPTIONS,
    mo,
    navigation_initial_page,
    set_navigation_page,
):
    navigation = mo.ui.radio(
        options=list(OPERATIONS_PAGE_OPTIONS),
        value=navigation_initial_page,
        label="",
        on_change=set_navigation_page,
    )
    return (navigation,)


@app.cell
def _(analysis_results, mo):
    get_analysis_results, set_analysis_results = mo.state(tuple(analysis_results))
    return get_analysis_results, set_analysis_results


@app.cell
def _(analysis_results, refresh_button, set_analysis_results):
    if refresh_button.value:
        set_analysis_results(tuple(analysis_results))
    return


@app.cell
def _(get_analysis_results):
    current_analysis_results = get_analysis_results()
    return (current_analysis_results,)


@app.cell
def _(OpcUaNodeMapping, operations_actions):
    def parse_opcua_mapping_lines(value: str):
        mappings = []
        for line_number, raw_line in enumerate(value.splitlines(), start=1):
            _line = raw_line.strip()
            if not _line:
                continue
            if "," not in _line:
                raise ValueError(f"Mapping line {line_number} must use signal_id,node_id")
            _channel_id, _node_id = _line.split(",", 1)
            mappings.append(
                OpcUaNodeMapping(
                    channel_id=_channel_id.strip(),
                    node_id=_node_id.strip(),
                )
            )
        return tuple(mappings)

    def run_setup_opcua_browse(*, endpoint_url: str, timeout_seconds: float):
        return operations_actions.browse_opcua(
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
        )

    return parse_opcua_mapping_lines, run_setup_opcua_browse


@app.cell
def _(collection_records, freshness_policies, lifecycle_records, mo, registered_sources):
    get_setup_config, set_setup_config = mo.state(
        (
            tuple(registered_sources),
            tuple(lifecycle_records),
            tuple(collection_records),
            tuple(freshness_policies),
        )
    )
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
        get_setup_config,
        get_setup_error,
        get_setup_success,
        set_file_discovery,
        set_file_discovery_signature,
        set_opcua_browse,
        set_opcua_browse_signature,
        set_pending_semantics,
        set_setup_config,
        set_setup_error,
        set_setup_success,
    )


@app.cell
def _(
    collection_records,
    freshness_policies,
    lifecycle_records,
    refresh_button,
    registered_sources,
    set_pending_semantics,
    set_setup_config,
    set_setup_error,
    set_setup_success,
):
    if refresh_button.value:
        set_setup_config(
            (
                tuple(registered_sources),
                tuple(lifecycle_records),
                tuple(collection_records),
                tuple(freshness_policies),
            )
        )
        set_pending_semantics({})
        set_setup_error("")
        set_setup_success("")
    return


@app.cell
def _(
    build_setup_workspace,
    get_setup_config,
    get_setup_error,
    get_setup_success,
):
    (
        setup_sources,
        setup_lifecycles,
        setup_collection,
        setup_freshness,
    ) = get_setup_config()
    setup_error = get_setup_error()
    setup_success = get_setup_success()
    setup_workspace = build_setup_workspace(
        sources=setup_sources,
        lifecycle_records=setup_lifecycles,
        collection_records=setup_collection,
        freshness_policies=setup_freshness,
    )
    return (
        setup_collection,
        setup_error,
        setup_freshness,
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
    if setup_selected_source is not None and setup_selected_source.source_type == SourceType.OPCUA:
        if setup_selected_source.collection_desired_state == CollectionDesiredState.RUNNING:
            setup_stop_collection_button = mo.ui.run_button(label="Stop collection")
        else:
            setup_start_collection_button = mo.ui.run_button(
                label="Start collection",
                kind="success",
            )
    return setup_start_collection_button, setup_stop_collection_button


@app.cell
def _(mo, setup_selected_source):
    if setup_selected_source is None:
        setup_freshness_age_input = None
        setup_save_freshness_button = None
        setup_clear_freshness_button = None
    else:
        _freshness_value = (
            ""
            if setup_selected_source.freshness_max_age_seconds is None
            else f"{setup_selected_source.freshness_max_age_seconds:g}"
        )
        setup_freshness_age_input = mo.ui.text(
            value=_freshness_value,
            label="Maximum data age (seconds)",
            full_width=True,
        )
        setup_save_freshness_button = mo.ui.run_button(label="Save data age policy")
        setup_clear_freshness_button = (
            None
            if setup_selected_source.freshness_max_age_seconds is None
            else mo.ui.run_button(label="Clear policy")
        )
    return (
        setup_clear_freshness_button,
        setup_freshness_age_input,
        setup_save_freshness_button,
    )


@app.cell
def _(
    datetime,
    get_setup_config,
    operations_actions,
    set_setup_config,
    set_setup_error,
    set_setup_success,
    setup_clear_freshness_button,
    setup_freshness_age_input,
    setup_save_freshness_button,
    setup_selected_source,
):
    _freshness_action = None
    if setup_save_freshness_button is not None and setup_save_freshness_button.value:
        _freshness_action = "save"
    elif setup_clear_freshness_button is not None and setup_clear_freshness_button.value:
        _freshness_action = "clear"

    if _freshness_action is not None:
        try:
            if setup_selected_source is None:
                raise ValueError("select a data source before changing its data age policy")
            _source_id = setup_selected_source.source_id
            if _freshness_action == "save":
                if setup_freshness_age_input is None:
                    raise ValueError("data age policy input is unavailable")
                _raw_value = setup_freshness_age_input.value.strip()
                if not _raw_value:
                    raise ValueError("maximum data age is required")
                _policy, _state = operations_actions.set_freshness_policy(
                    _source_id,
                    max_observation_age_seconds=float(_raw_value),
                    changed_at=datetime.now().astimezone(),
                )
                if _policy is None:
                    raise AssertionError("saved freshness policy unexpectedly missing")
                _message = (
                    f"Data age policy saved: {_source_id} · "
                    f"{_policy.max_observation_age_seconds:g} s."
                )
            else:
                _, _state = operations_actions.set_freshness_policy(
                    _source_id,
                    max_observation_age_seconds=None,
                    changed_at=datetime.now().astimezone(),
                )
                _message = f"Data age policy cleared: {_source_id}."
        except (LookupError, OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            _, _, _collection, _ = get_setup_config()
            set_setup_config(
                (_state.sources, _state.lifecycles, _collection, _state.freshness_policies)
            )
            set_setup_error("")
            set_setup_success(_message)
    return


@app.cell
def _(SourceType, mo, setup_selected_source):
    if setup_selected_source is None:
        setup_run_diagnostic_button = None
        setup_subscription_diagnostic_button = None
    else:
        setup_run_diagnostic_button = mo.ui.run_button(label="Run one diagnostic cycle")
        setup_subscription_diagnostic_button = (
            mo.ui.run_button(label="Collect bounded subscription")
            if setup_selected_source.source_type == SourceType.OPCUA
            else None
        )
    return setup_run_diagnostic_button, setup_subscription_diagnostic_button


@app.cell
def _(mo):
    get_setup_diagnostic_error, set_setup_diagnostic_error = mo.state("")
    get_setup_diagnostic_success, set_setup_diagnostic_success = mo.state("")
    return (
        get_setup_diagnostic_error,
        get_setup_diagnostic_success,
        set_setup_diagnostic_error,
        set_setup_diagnostic_success,
    )


@app.cell
def _(
    OperationsDiagnosticKind,
    SourceRuntimeCycleState,
    get_setup_config,
    operations_actions,
    set_setup_config,
    set_setup_diagnostic_error,
    set_setup_diagnostic_success,
    setup_run_diagnostic_button,
    setup_selected_source,
    setup_subscription_diagnostic_button,
):
    _diagnostic_kind = None
    if setup_run_diagnostic_button is not None and setup_run_diagnostic_button.value:
        _diagnostic_kind = OperationsDiagnosticKind.CYCLE
    elif (
        setup_subscription_diagnostic_button is not None
        and setup_subscription_diagnostic_button.value
    ):
        _diagnostic_kind = OperationsDiagnosticKind.SUBSCRIPTION

    if _diagnostic_kind is not None:
        try:
            if setup_selected_source is None:
                raise ValueError("select a data source before running diagnostics")
            _result, _state = operations_actions.run_diagnostic(
                setup_selected_source.source_id,
                kind=_diagnostic_kind,
            )
        except (LookupError, OSError, RuntimeError, ValueError) as error:
            set_setup_diagnostic_success("")
            set_setup_diagnostic_error(str(error))
        else:
            _, _, _collection, _freshness = get_setup_config()
            set_setup_config((_state.sources, _state.lifecycles, _collection, _freshness))
            if _result.state == SourceRuntimeCycleState.SUCCEEDED:
                _message = (
                    "Diagnostic cycle completed."
                    if _diagnostic_kind == OperationsDiagnosticKind.CYCLE
                    else "Bounded subscription completed."
                )
                set_setup_diagnostic_error("")
                set_setup_diagnostic_success(
                    _message + " Use Refresh to reload current runtime evidence in Monitor."
                )
            elif _result.state == SourceRuntimeCycleState.SKIPPED:
                set_setup_diagnostic_success("")
                set_setup_diagnostic_error(_result.message or "diagnostic action skipped")
            else:
                _scope = "unknown" if _result.failure_scope is None else _result.failure_scope.value
                set_setup_diagnostic_success("")
                set_setup_diagnostic_error(
                    f"{_scope} failure · {_result.message or 'diagnostic action failed'}"
                )
    return


@app.cell
def _(get_setup_diagnostic_error, get_setup_diagnostic_success):
    setup_diagnostic_error = get_setup_diagnostic_error()
    setup_diagnostic_success = get_setup_diagnostic_success()
    return setup_diagnostic_error, setup_diagnostic_success


@app.cell
def _(
    SourceLifecycleState,
    datetime,
    get_setup_config,
    operations_actions,
    set_setup_config,
    set_setup_error,
    set_setup_success,
    setup_enable_button,
    setup_pause_button,
    setup_selected_source,
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
            _record, _state = operations_actions.transition_source(
                setup_selected_source.source_id,
                _setup_lifecycle_target,
                changed_at=datetime.now().astimezone(),
            )
        except (LookupError, OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            _, _, _current_collection, _current_freshness = get_setup_config()
            set_setup_config(
                (_state.sources, _state.lifecycles, _current_collection, _current_freshness)
            )
            set_setup_error("")
            set_setup_success(f"Source use changed: {_record.source_id} → {_record.state.value}.")
    return


@app.cell
def _(
    CollectionDesiredState,
    datetime,
    get_setup_config,
    operations_actions,
    set_setup_config,
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
            _record, _records = operations_actions.request_collection(
                setup_selected_source.source_id,
                _setup_collection_target,
                requested_at=datetime.now().astimezone(),
            )
        except (LookupError, OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            (
                _current_sources,
                _current_lifecycles,
                _,
                _current_freshness,
            ) = get_setup_config()
            set_setup_config((_current_sources, _current_lifecycles, _records, _current_freshness))
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
        )
    else:
        file_signal_selection = None
    return file_discovery, file_discovery_current, file_signal_selection


@app.cell
def _(
    OperationsActionError,
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
        except (OperationsActionError, ValueError) as error:
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
    opcua_browse_current = opcua_browse is not None and opcua_browse_signature == _opcua_signature
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
            _definition = MeasurementDefinition(
                observed_property=semantic_observed_property_input.value.strip() or None,
                scope=semantic_scope_input.value.strip() or None,
                statistic=semantic_statistic_input.value.strip() or None,
                unit=semantic_unit_input.value.strip() or None,
                unit_evidence=semantic_unit_evidence_input.value.strip() or None,
            )
            if not any(
                (
                    _definition.observed_property,
                    _definition.scope,
                    _definition.statistic,
                    _definition.unit,
                )
            ):
                raise ValueError("provide explicit measurement meaning or choose Keep unresolved")
            _binding = ChannelSemanticBinding(
                source_id=_source_id,
                channel_id=_channel_id,
                version=semantic_version_input.value.strip(),
                definition=_definition,
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
    elif (
        semantic_clear_button is not None
        and semantic_clear_button.value
        and semantic_channel_input is not None
    ):
        _current = dict(get_pending_semantics())
        _current.pop(semantic_channel_input.value, None)
        set_pending_semantics(_current)
        set_setup_error("")
        set_setup_success(f"{semantic_channel_input.value} will remain unresolved.")
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
    ChannelSemanticBinding,
    FileSourceConfig,
    FileSourceMode,
    OpcUaSourceConfig,
    RegisteredSource,
    add_asset_id,
    add_point_id,
    add_source_id,
    add_source_name,
    add_source_type,
    datetime,
    file_discovery,
    file_discovery_current,
    file_mode_input,
    file_path_input,
    file_sampling_rate_input,
    file_signal_selection,
    file_timestamp_input,
    get_setup_config,
    operations_actions,
    opcua_candidate_mappings,
    opcua_endpoint_input,
    opcua_mapping_error,
    opcua_timeout_input,
    pending_semantics,
    register_setup_source_button,
    set_pending_semantics,
    set_setup_config,
    set_setup_error,
    set_setup_success,
):
    if register_setup_source_button.value:
        try:
            _source_id = add_source_id.value.strip()
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
                    raise ValueError("timestamp column was not discovered in every CSV file")
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
                            ChannelSemanticBinding(
                                source_id=_source_id,
                                channel_id=channel,
                                version=_binding_by_channel[channel].version,
                                definition=_binding_by_channel[channel].definition,
                                interpretation_evidence=(
                                    _binding_by_channel[channel].interpretation_evidence
                                ),
                            )
                            for channel in sorted(_binding_by_channel)
                        ),
                    ),
                    registered_at=datetime.now().astimezone(),
                )

            _state = operations_actions.register_source(_candidate)
        except (OSError, ValueError) as error:
            set_setup_success("")
            set_setup_error(str(error))
        else:
            _, _, _current_collection, _current_freshness = get_setup_config()
            set_setup_config(
                (_state.sources, _state.lifecycles, _current_collection, _current_freshness)
            )
            set_pending_semantics({})
            set_setup_error("")
            set_setup_success(f"Source saved: {_candidate.source_id}. Enable it when ready to use.")
    return


@app.cell
def _(mo):
    get_asset_selection, set_asset_selection = mo.state(None)
    get_asset_section, set_asset_section = mo.state("Overview")
    return (
        get_asset_section,
        get_asset_selection,
        set_asset_section,
        set_asset_selection,
    )


@app.cell
def _(
    asset_names,
    get_asset_section,
    get_asset_selection,
    history_assets,
    mo,
    monitor,
    set_asset_section,
    set_asset_selection,
):
    _asset_ids = tuple(
        sorted(
            {
                *(item.asset_id for item in monitor.assets),
                *(item.asset_id for item in history_assets),
            }
        )
    )
    if _asset_ids:
        _requested_asset_id = get_asset_selection()
        _selected_asset_id = (
            _requested_asset_id if _requested_asset_id in _asset_ids else _asset_ids[0]
        )
        asset_selector = mo.ui.dropdown(
            options={asset_names.option_label(asset_id): asset_id for asset_id in _asset_ids},
            value=asset_names.option_label(_selected_asset_id),
            label="Asset",
            full_width=True,
            on_change=set_asset_selection,
        )
    else:
        asset_selector = None
    _asset_sections = ["Overview", "Signals", "Analysis", "Events", "Maintenance"]
    _requested_section = get_asset_section()
    asset_section = mo.ui.radio(
        options=_asset_sections,
        value=_requested_section if _requested_section in _asset_sections else "Overview",
        label="View",
        on_change=set_asset_section,
    )
    return asset_section, asset_selector


@app.cell
def _(
    AssetIdentity,
    OperationsReadError,
    acquisition_surfaces,
    current_analysis_results,
    asset_selector,
    build_asset_detail,
    build_asset_workspace_view,
    history_assets,
    history_reader,
    investigation_findings,
    list_operations_history_channels,
    live_flow_timing,
    maintenance_events,
    monitor,
    navigation,
    overview,
    registered_sources,
    skipped_analysis_attempts,
):
    asset_workspace = None
    asset_workspace_error = None
    asset_history_error = None
    if navigation.value in {"Assets", "Monitor"} and asset_selector is not None:
        _selected_asset_id = asset_selector.value
        _history_summary = next(
            (item for item in history_assets if item.asset_id == _selected_asset_id),
            None,
        )
        _history_channels = ()
        if history_reader is not None:
            try:
                _history_channels = list_operations_history_channels(
                    history_reader,
                    _selected_asset_id,
                )
            except OperationsReadError as error:
                asset_history_error = str(error)
        _detail = build_asset_detail(
            AssetIdentity(_selected_asset_id),
            sources=registered_sources,
            overview=overview,
            analysis_runs=tuple(item.run for item in current_analysis_results),
            findings=investigation_findings,
            review_events=maintenance_events,
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
            analysis_results=current_analysis_results,
            monitor_asset=_monitor_asset,
            history_summary=_history_summary,
            history_channels=_history_channels,
            acquisition_surfaces=_asset_surfaces,
            live_flow_timing=live_flow_timing,
            skipped_analysis_attempts=skipped_analysis_attempts,
        )
    return asset_history_error, asset_workspace, asset_workspace_error


@app.cell
def _(FileSourceConfig, FileSourceMode, asset_workspace, mo, registered_sources):
    if asset_workspace is None:
        asset_file_analysis_source = None
        asset_run_file_analysis_button = None
    else:
        _file_candidates = tuple(
            source
            for source in registered_sources
            if source.asset_id == asset_workspace.asset_id
            and isinstance(source.config, FileSourceConfig)
            and source.config.mode == FileSourceMode.SNAPSHOT
        )
        if _file_candidates:
            _options = {
                f"{source.name} · {source.source_id}": source.source_id
                for source in _file_candidates
            }
            asset_file_analysis_source = mo.ui.dropdown(
                options=list(_options),
                value=next(iter(_options)),
                label="FILE snapshot source",
                full_width=True,
            )
            asset_run_file_analysis_button = mo.ui.run_button(
                label="Analyze FILE snapshot",
                kind="success",
            )
        else:
            asset_file_analysis_source = None
            asset_run_file_analysis_button = None
    return asset_file_analysis_source, asset_run_file_analysis_button


@app.cell
def _(mo):
    get_asset_analysis_action_error, set_asset_analysis_action_error = mo.state("")
    get_asset_analysis_action_success, set_asset_analysis_action_success = mo.state("")
    return (
        get_asset_analysis_action_error,
        get_asset_analysis_action_success,
        set_asset_analysis_action_error,
        set_asset_analysis_action_success,
    )


@app.cell
def _(
    FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID,
    asset_file_analysis_source,
    asset_run_file_analysis_button,
    get_analysis_results,
    operations_actions,
    registered_sources,
    set_analysis_results,
    set_asset_analysis_action_error,
    set_asset_analysis_action_success,
):
    if asset_run_file_analysis_button is not None and asset_run_file_analysis_button.value:
        try:
            if asset_file_analysis_source is None:
                raise ValueError("select a FILE snapshot source before analysis")
            _selected_label = asset_file_analysis_source.value
            _source_id = _selected_label.rsplit(" · ", 1)[-1]
            _source = next(
                source for source in registered_sources if source.source_id == _source_id
            )
            _, _file_feature_results = operations_actions.record_file_analysis(_source)
            _other_results = tuple(
                item
                for item in get_analysis_results()
                if item.evidence.capability_id != FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID
            )
            _updated_results = tuple(
                sorted(
                    (*_other_results, *_file_feature_results),
                    key=lambda item: (item.run.completed_at, item.run.analysis_run_id),
                )
            )
        except (LookupError, OSError, ValueError) as error:
            set_asset_analysis_action_success("")
            set_asset_analysis_action_error(str(error))
        else:
            set_analysis_results(_updated_results)
            set_asset_analysis_action_error("")
            set_asset_analysis_action_success(
                "FILE snapshot analysis recorded. Assets and Investigations now use the "
                "persisted evidence. This does not create anomaly, fault, health, or "
                "maintenance meaning."
            )
    return


@app.cell
def _(get_asset_analysis_action_error, get_asset_analysis_action_success):
    asset_analysis_action_error = get_asset_analysis_action_error()
    asset_analysis_action_success = get_asset_analysis_action_success()
    return asset_analysis_action_error, asset_analysis_action_success


@app.cell
def _(
    asset_analysis_action_error,
    asset_analysis_action_success,
    asset_file_analysis_source,
    asset_run_file_analysis_button,
    asset_workspace,
    mo,
    render_asset_analysis_html,
):
    if asset_workspace is None:
        asset_analysis_view = mo.md("No asset is selected.")
    else:
        _blocks = [mo.Html(render_asset_analysis_html(asset_workspace))]
        if asset_analysis_action_error:
            _blocks.append(
                mo.callout(
                    asset_analysis_action_error,
                    kind="danger",
                    title="FILE analysis failed",
                )
            )
        if asset_analysis_action_success:
            _blocks.append(
                mo.callout(
                    asset_analysis_action_success,
                    kind="success",
                    title="Analysis recorded",
                )
            )
        if asset_file_analysis_source is not None and asset_run_file_analysis_button is not None:
            _blocks.extend(
                [
                    mo.md("### Analyze prepared FILE snapshot"),
                    asset_file_analysis_source,
                    asset_run_file_analysis_button,
                    mo.md(
                        "This action computes and stores versioned vibration statistical "
                        "feature evidence from the exact registered snapshot. It does not "
                        "declare anomaly, fault, health state, or maintenance need."
                    ),
                ]
            )
        else:
            _blocks.append(
                mo.md(
                    "No registered FILE snapshot source is available for on-demand "
                    "feature analysis on this asset."
                )
            )
        asset_analysis_view = mo.vstack(_blocks, gap=0.8)
    return (asset_analysis_view,)


@app.cell
def _(mo):
    get_signal_channel_choice, set_signal_channel_choice = mo.state(None)
    return get_signal_channel_choice, set_signal_channel_choice


@app.cell
def _(
    asset_workspace,
    get_signal_channel_choice,
    initial_signal_channel,
    mo,
    registered_sources,
    set_signal_channel_choice,
):
    if asset_workspace is None:
        signal_channel_selector = None
    else:
        _confirmed = {
            binding.channel_id
            for source in registered_sources
            if source.asset_id == asset_workspace.asset_id
            for binding in getattr(source.config, "semantic_bindings", ())
            if binding.definition.observed_property is not None
        }
        _channel_ids = tuple(
            sorted(
                {
                    *asset_workspace.history_channels,
                    *(
                        identity.channel_id
                        for source in registered_sources
                        if source.asset_id == asset_workspace.asset_id
                        for identity in source.channel_identities
                    ),
                }
            )
        )
        if _channel_ids:
            signal_channel_selector = mo.ui.dropdown(
                options=list(_channel_ids),
                value=initial_signal_channel(
                    _channel_ids,
                    confirmed_channel_ids=_confirmed,
                    selected=get_signal_channel_choice(),
                ),
                label="Signal",
                full_width=True,
                on_change=set_signal_channel_choice,
            )
        else:
            signal_channel_selector = None
    signal_range_selector = mo.ui.radio(
        options=["Live", "15m", "24h", "7d"],
        value="Live",
        label="Time range",
    )
    return signal_channel_selector, signal_range_selector


@app.cell
def _(mo):
    monitor_trend_range_selector = mo.ui.radio(
        options=["15m", "1h", "24h", "7d"],
        value="1h",
        label="Overview range",
    )
    return (monitor_trend_range_selector,)


@app.cell
def _(mo):
    live_signal_refresh = mo.ui.refresh(default_interval="1s")
    return (live_signal_refresh,)


@app.cell
def _(
    OperationsReadError,
    assessed_at,
    asset_selector,
    history_reader,
    latest_measurement_rows,
    mo,
    navigation,
    query_operations_latest_asset_measurements,
    render_monitor_signal_overview_html,
    signal_channel_selector,
):
    monitor_latest_points = ()
    monitor_latest_rows = ()
    if navigation.value != "Monitor" or asset_selector is None:
        monitor_signal_overview = mo.md("")
    elif history_reader is None:
        monitor_signal_overview = mo.md(
            "### Latest stored observations\n\n"
            "No Asset History catalog is available for this workspace."
        )
    else:
        try:
            monitor_latest_points = query_operations_latest_asset_measurements(
                history_reader,
                asset_selector.value,
                limit=1000,
            )
            monitor_latest_rows = tuple(
                latest_measurement_rows(
                    monitor_latest_points,
                    as_of=assessed_at,
                )
            )
        except OperationsReadError as error:
            monitor_latest_points = ()
            monitor_latest_rows = ()
            monitor_signal_overview = mo.callout(
                str(error),
                kind="danger",
                title="Latest stored observations unavailable",
            )
        else:
            _selected_channel = (
                None if signal_channel_selector is None else signal_channel_selector.value
            )
            monitor_signal_overview = mo.Html(
                render_monitor_signal_overview_html(
                    monitor_latest_rows,
                    selected_channel=_selected_channel,
                    primary_limit=8,
                )
            )
    return monitor_latest_points, monitor_latest_rows, monitor_signal_overview


@app.cell
def _(
    OperationsReadError,
    asset_selector,
    history_reader,
    investigation_capability_label,
    investigation_queue,
    mo,
    monitor_latest_points,
    monitor_latest_rows,
    monitor_signal_channels,
    monitor_trend_range_selector,
    navigation,
    query_operations_multi_signal_measurement_aggregation,
    render_multi_signal_measurement_aggregation_svg,
    resolve_measurement_range,
    signal_channel_selector,
):
    monitor_trend_start_at = None
    monitor_trend_end_at = None
    monitor_window_evidence_items = ()
    if navigation.value != "Monitor" or asset_selector is None or history_reader is None:
        monitor_signal_trends = mo.md("")
    else:
        _event_times = tuple(
            point.measurement.event_at
            for point in monitor_latest_points
            if point.measurement.event_at is not None
        )
        _selected_channel = (
            None if signal_channel_selector is None else signal_channel_selector.value
        )
        _channels = monitor_signal_channels(
            monitor_latest_rows,
            selected_channel=_selected_channel,
            limit=6,
        )
        if not _event_times or not _channels:
            monitor_signal_trends = mo.md(
                "### Recent signal trends\n\nNo event-time observations are available to compare."
            )
        else:
            _anchor_at = max(_event_times)
            _range_id = monitor_trend_range_selector.value
            _start_at, _end_at = resolve_measurement_range(
                _range_id,
                as_of=_anchor_at,
                start_at=_anchor_at,
                end_at=_anchor_at,
            )
            monitor_trend_start_at = _start_at
            monitor_trend_end_at = _end_at
            monitor_window_evidence_items = tuple(
                item
                for item in investigation_queue.items
                if item.asset_id == asset_selector.value
                and item.observed_end_at >= _start_at
                and item.observed_start_at <= _end_at
            )[:6]
            _evidence_windows = tuple(
                (
                    item.observed_start_at,
                    item.observed_end_at,
                    investigation_capability_label(item.capability_id),
                )
                for item in monitor_window_evidence_items
            )
            _bucket_count = {
                "15m": 90,
                "1h": 120,
                "24h": 144,
                "7d": 168,
            }[_range_id]
            try:
                _multi_signal = query_operations_multi_signal_measurement_aggregation(
                    history_reader,
                    asset_selector.value,
                    channel_ids=_channels,
                    start_at=_start_at,
                    end_at=_end_at,
                    bucket_count=_bucket_count,
                )
            except OperationsReadError as error:
                monitor_signal_trends = mo.callout(
                    str(error),
                    kind="danger",
                    title="Signal trends unavailable",
                )
            else:
                _window_end = _anchor_at.isoformat()
                _evidence_count = len(monitor_window_evidence_items)
                _evidence_note = (
                    "No analysis evidence overlaps this event-time window."
                    if _evidence_count == 0
                    else f"{_evidence_count} analysis evidence window(s) overlap this range."
                )
                monitor_signal_trends = mo.vstack(
                    [
                        mo.hstack(
                            [
                                monitor_trend_range_selector,
                                mo.md(
                                    "**Recent signal trends**  \n"
                                    f"Latest recorded event-time: `{_window_end}`"
                                ),
                            ],
                            widths=[0.34, 0.66],
                            align="end",
                        ),
                        mo.Html(
                            render_multi_signal_measurement_aggregation_svg(
                                _multi_signal,
                                selected_channel=_selected_channel,
                                evidence_windows=_evidence_windows,
                            )
                        ),
                        mo.md(
                            f"{_evidence_note} "
                            "Each signal keeps its own unit while sharing the same UTC time axis. "
                            "Buckets show stored min/max/mean only; null, non-good and conflicting "
                            "observations are marked as excluded evidence. No interpolation, "
                            "cross-signal normalization, asset health or alarm state is inferred."
                        ),
                    ],
                    gap=0.7,
                )
    return (
        monitor_signal_trends,
        monitor_trend_end_at,
        monitor_trend_start_at,
        monitor_window_evidence_items,
    )


@app.cell
def _(
    UTC,
    investigation_capability_label,
    investigation_review_label,
    mo,
    monitor_window_evidence_items,
):
    if monitor_window_evidence_items:
        monitor_evidence_label_to_id = {
            (
                f"{investigation_capability_label(item.capability_id)} · "
                f"{item.observed_start_at.astimezone(UTC).strftime('%H:%M:%S')} - "
                f"{item.observed_end_at.astimezone(UTC).strftime('%H:%M:%S')} UTC · "
                f"{investigation_review_label(item.review_state)} · {index + 1}"
            ): item.investigation_id
            for index, item in enumerate(monitor_window_evidence_items)
        }
        monitor_evidence_selector = mo.ui.dropdown(
            options=list(monitor_evidence_label_to_id),
            value=next(iter(monitor_evidence_label_to_id)),
            label="Analysis evidence",
            full_width=True,
        )
        monitor_evidence_open_button = mo.ui.run_button(
            label="Open investigation",
        )
    else:
        monitor_evidence_label_to_id = {}
        monitor_evidence_selector = None
        monitor_evidence_open_button = None
    return (
        monitor_evidence_label_to_id,
        monitor_evidence_open_button,
        monitor_evidence_selector,
    )


@app.cell
def _(
    monitor_evidence_label_to_id,
    monitor_evidence_selector,
    monitor_window_evidence_items,
):
    selected_monitor_evidence = None
    if monitor_evidence_selector is not None:
        _investigation_id = monitor_evidence_label_to_id[monitor_evidence_selector.value]
        selected_monitor_evidence = next(
            item
            for item in monitor_window_evidence_items
            if item.investigation_id == _investigation_id
        )
    return (selected_monitor_evidence,)


@app.cell
def _(
    investigation_queue,
    resolve_investigation_route,
    selected_monitor_evidence,
):
    monitor_evidence_route = None
    monitor_evidence_route_error = ""
    if selected_monitor_evidence is not None:
        try:
            monitor_evidence_route = resolve_investigation_route(
                selected_monitor_evidence.investigation_id,
                investigation_queue=investigation_queue,
            )
        except LookupError as error:
            monitor_evidence_route_error = str(error)
    return monitor_evidence_route, monitor_evidence_route_error


@app.cell
def _(
    monitor_evidence_open_button,
    monitor_evidence_route,
    set_investigation_asset_filter,
    set_investigation_capability_filter,
    set_investigation_review_filter,
    set_investigation_selection,
    set_navigation_page,
):
    if (
        monitor_evidence_open_button is not None
        and monitor_evidence_open_button.value
        and monitor_evidence_route is not None
    ):
        set_investigation_review_filter("All")
        set_investigation_asset_filter("All")
        set_investigation_capability_filter("All")
        set_investigation_selection(
            (
                monitor_evidence_route.investigation_group_id,
                monitor_evidence_route.investigation_id,
            )
        )
        set_navigation_page("Investigations")
    return


@app.cell
def _(
    UTC,
    investigation_capability_label,
    investigation_review_label,
    mo,
    monitor_evidence_open_button,
    monitor_evidence_route_error,
    monitor_evidence_selector,
    monitor_window_evidence_items,
):
    if not monitor_window_evidence_items:
        monitor_evidence_view = None
    else:
        _rows = [
            {
                "Capability": investigation_capability_label(item.capability_id),
                "Observed start": item.observed_start_at.astimezone(UTC).isoformat(),
                "Observed end": item.observed_end_at.astimezone(UTC).isoformat(),
                "Source": item.source_id,
                "Point": item.measurement_point_id or "—",
                "Data quality": item.data_quality,
                "Review": investigation_review_label(item.review_state),
            }
            for item in monitor_window_evidence_items
        ]
        _blocks = [
            mo.md(
                "### Analysis evidence in this window\n\n"
                "Shaded ranges on the signal charts are persisted analysis observation windows."
            ),
            mo.ui.table(_rows, page_size=6, selection=None),
        ]
        if monitor_evidence_selector is not None and monitor_evidence_open_button is not None:
            _blocks.append(
                mo.hstack(
                    [monitor_evidence_selector, monitor_evidence_open_button],
                    widths=[0.72, 0.28],
                    align="end",
                )
            )
        if monitor_evidence_route_error:
            _blocks.append(
                mo.callout(
                    monitor_evidence_route_error,
                    kind="danger",
                    title="Analysis drill-down unavailable",
                )
            )
        monitor_evidence_view = mo.vstack(_blocks, gap=0.6)
    return (monitor_evidence_view,)


@app.cell
def _(
    OperationsReadError,
    UTC,
    asset_history_error,
    asset_section,
    asset_selector,
    asset_workspace,
    assessed_at,
    datetime,
    history_reader,
    latest_measurement_rows,
    live_observation_css,
    live_observation_recent_page,
    live_flow_timing,
    live_signal_refresh,
    load_operations_live_observation,
    measurement_aggregation_rows,
    measurement_aggregation_summary,
    measurement_history_range_summary,
    measurement_history_rows,
    mo,
    navigation,
    operations_context,
    query_operations_latest_measurements,
    query_operations_measurement_aggregation,
    query_operations_measurement_page,
    registered_sources,
    render_live_observation_html,
    render_measurement_aggregation_svg,
    render_measurement_history_svg,
    resolve_measurement_range,
    signal_channel_selector,
    signal_range_selector,
):
    if navigation.value not in {"Monitor", "Assets"} or (
        navigation.value == "Assets" and asset_section.value != "Signals"
    ):
        signal_view = mo.md("")
    elif asset_workspace is None:
        signal_view = mo.md("No asset is selected.")
    elif asset_history_error:
        signal_view = mo.callout(
            asset_history_error,
            kind="danger",
            title="Asset History unavailable",
        )
    elif signal_channel_selector is None:
        signal_view = mo.md(
            "### Signals\n\nNo mapped or stored signal is available for this asset yet."
        )
    elif asset_selector is None:
        signal_view = mo.md("### Signals\n\nNo asset is selected.")
    else:
        try:
            _channel_id = signal_channel_selector.value
            _range_id = signal_range_selector.value

            if _range_id == "Live":
                _live_tick = live_signal_refresh.value
                del _live_tick
                _sampled_at = datetime.now(UTC)
                _live = load_operations_live_observation(
                    operations_context.snapshot.paths,
                    asset_id=asset_selector.value,
                    channel_id=_channel_id,
                    registered_sources=registered_sources,
                    asset_sources=asset_workspace.sources,
                    sampled_at=_sampled_at,
                    lookback_seconds=60.0,
                    point_budget=600,
                )
                _live_page = live_observation_recent_page(_live)
                _controls = mo.hstack(
                    [signal_channel_selector, signal_range_selector, live_signal_refresh],
                    widths=[0.48, 0.32, 0.20],
                    align="start",
                )
                _live_blocks = [
                    mo.Html(live_observation_css()),
                    _controls,
                    mo.Html(
                        render_live_observation_html(
                            _live,
                            silence_limit_seconds=live_flow_timing.max_silence.total_seconds(),
                        )
                    ),
                    mo.md("#### Recent stored event-time points"),
                ]
                if _live_page.points:
                    _live_blocks.extend(
                        [
                            mo.Html(render_measurement_history_svg(_live_page)),
                            mo.accordion(
                                {
                                    "Raw observations": mo.ui.table(
                                        measurement_history_rows(_live_page),
                                        page_size=10,
                                    )
                                }
                            ),
                        ]
                    )
                else:
                    _live_blocks.append(
                        mo.md(
                            "No persisted observation is available in the live source's "
                            "recent event-time window yet."
                        )
                    )
                _live_blocks.append(
                    mo.md(
                        "Source flow uses collector/session evidence; selected-channel "
                        "quality and event time use stored observation evidence. "
                        "The trend draws raw points "
                        "without interpolation, so unobserved intervals remain visually unfilled. "
                        "Historical replay timestamps remain historical. This view does not infer "
                        "asset health, fault, alarm, or expected missing samples."
                    )
                )
                signal_view = mo.vstack(_live_blocks, gap=1.0)
            elif history_reader is None:
                signal_view = mo.md(
                    "### Signals\n\nNo Asset History catalog is available for this workspace."
                )
            else:
                _start_at, _end_at = resolve_measurement_range(
                    _range_id,
                    as_of=assessed_at,
                    start_at=assessed_at,
                    end_at=assessed_at,
                )
                _latest = query_operations_latest_measurements(
                    history_reader,
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
                    _aggregation = query_operations_measurement_aggregation(
                        history_reader,
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
                    _page = query_operations_measurement_page(
                        history_reader,
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
                            "This view does not infer asset health, fault, alarm, "
                            "or missing samples."
                        ),
                    ],
                    gap=1.0,
                )
        except OperationsReadError as error:
            signal_view = mo.callout(
                str(error),
                kind="danger",
                title="Signals unavailable",
            )
    return (signal_view,)


@app.cell
def _(mo):
    get_investigation_selection, set_investigation_selection = mo.state((None, None))
    get_investigation_review_filter, set_investigation_review_filter = mo.state("All")
    get_investigation_asset_filter, set_investigation_asset_filter = mo.state("All")
    get_investigation_capability_filter, set_investigation_capability_filter = mo.state("All")
    return (
        get_investigation_asset_filter,
        get_investigation_capability_filter,
        get_investigation_review_filter,
        get_investigation_selection,
        set_investigation_asset_filter,
        set_investigation_capability_filter,
        set_investigation_review_filter,
        set_investigation_selection,
    )


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
    current_analysis_results,
    build_investigation_queue,
    get_review_workflow,
):
    investigation_findings, maintenance_events = get_review_workflow()
    investigation_queue = build_investigation_queue(
        analysis_results=current_analysis_results,
        findings=investigation_findings,
        review_events=maintenance_events,
    )
    return investigation_findings, maintenance_events, investigation_queue


@app.cell
def _(
    investigation_findings,
    maintenance_events,
    operations_context,
    project_review_workflow,
):
    # A review action in this session updates the review-dependent projections
    # (Monitor counts, attention, asset review state) without reloading other state.
    _review_projection = project_review_workflow(
        operations_context.snapshot,
        findings=investigation_findings,
        review_events=maintenance_events,
    )
    overview = _review_projection.overview
    monitor = _review_projection.monitor
    return monitor, overview


@app.cell
def _(
    asset_names,
    InvestigationReviewState,
    get_investigation_asset_filter,
    get_investigation_capability_filter,
    get_investigation_review_filter,
    investigation_capability_label,
    investigation_queue,
    investigation_review_label,
    mo,
    set_investigation_asset_filter,
    set_investigation_capability_filter,
    set_investigation_review_filter,
):
    _review_options = ["All"] + [
        investigation_review_label(state) for state in InvestigationReviewState
    ]
    _review_value = get_investigation_review_filter()
    investigation_review_filter = mo.ui.dropdown(
        options=_review_options,
        value=_review_value if _review_value in _review_options else "All",
        label="Review",
        full_width=True,
        on_change=set_investigation_review_filter,
    )
    _asset_options = {
        "All": "All",
        **{
            asset_names.option_label(asset_id): asset_id
            for asset_id in investigation_queue.asset_ids
        },
    }
    _asset_value = get_investigation_asset_filter()
    investigation_asset_filter = mo.ui.dropdown(
        options=_asset_options,
        value=(
            asset_names.option_label(_asset_value)
            if _asset_value in investigation_queue.asset_ids
            else "All"
        ),
        label="Asset",
        full_width=True,
        on_change=set_investigation_asset_filter,
    )
    _capability_labels = {
        investigation_capability_label(capability_id): capability_id
        for capability_id in investigation_queue.capability_ids
    }
    _capability_options = ["All", *_capability_labels]
    _capability_value = get_investigation_capability_filter()
    investigation_capability_filter = mo.ui.dropdown(
        options=_capability_options,
        value=_capability_value if _capability_value in _capability_options else "All",
        label="Capability",
        full_width=True,
        on_change=set_investigation_capability_filter,
    )
    return (
        investigation_asset_filter,
        investigation_capability_filter,
        investigation_review_filter,
    )


@app.cell
def _(
    asset_names,
    InvestigationReviewState,
    investigation_asset_filter,
    investigation_capability_filter,
    investigation_capability_label,
    investigation_group_option_label,
    investigation_queue,
    investigation_review_filter,
    investigation_review_label,
    get_investigation_selection,
    mo,
    set_investigation_selection,
):
    _review_state_by_label = {
        investigation_review_label(state): state for state in InvestigationReviewState
    }
    _capability_by_label = {
        investigation_capability_label(capability_id): capability_id
        for capability_id in investigation_queue.capability_ids
    }
    _groups = investigation_queue.groups(
        review_state=_review_state_by_label.get(investigation_review_filter.value),
        asset_id=(
            None if investigation_asset_filter.value == "All" else investigation_asset_filter.value
        ),
        capability_id=_capability_by_label.get(investigation_capability_filter.value),
    )
    _group_label_to_id = {
        f"{investigation_group_option_label(group, asset_names)} · {index + 1}": group.group_id
        for index, group in enumerate(_groups)
    }
    _group_id_to_label = {value: key for key, value in _group_label_to_id.items()}
    if _groups:
        _requested_group_id, _ = get_investigation_selection()
        _selected_group_id = (
            _requested_group_id
            if _requested_group_id in _group_id_to_label
            else _groups[0].group_id
        )
        investigation_group_selector = mo.ui.radio(
            options=list(_group_label_to_id),
            value=_group_id_to_label[_selected_group_id],
            label="Queue groups",
            on_change=lambda value: set_investigation_selection(
                (_group_label_to_id[value], None),
            ),
        )
    else:
        investigation_group_selector = None
    investigation_group_count = len(_groups)
    investigation_group_label_to_id = _group_label_to_id
    return (
        investigation_group_count,
        investigation_group_label_to_id,
        investigation_group_selector,
    )


@app.cell
def _(
    investigation_group_label_to_id,
    investigation_group_selector,
    investigation_queue,
):
    investigation_selected_group_id = (
        None
        if investigation_group_selector is None
        else investigation_group_label_to_id[investigation_group_selector.value]
    )
    selected_investigation_group = None
    if investigation_selected_group_id is not None:
        selected_investigation_group = next(
            (
                group
                for group in investigation_queue.groups()
                if group.group_id == investigation_selected_group_id
            ),
            None,
        )
    return investigation_selected_group_id, selected_investigation_group


@app.cell
def _(
    asset_names,
    get_investigation_selection,
    investigation_queue_option_label,
    mo,
    selected_investigation_group,
    set_investigation_selection,
):
    if selected_investigation_group is None:
        investigation_selector = None
        investigation_label_to_id = {}
    else:
        _label_to_id = {
            f"{investigation_queue_option_label(item, asset_names)} · {index + 1}": (
                item.investigation_id
            )
            for index, item in enumerate(selected_investigation_group.items)
        }
        _id_to_label = {value: key for key, value in _label_to_id.items()}
        _, _requested_investigation_id = get_investigation_selection()
        _selected_id = (
            _requested_investigation_id
            if _requested_investigation_id in _id_to_label
            else selected_investigation_group.items[0].investigation_id
        )
        investigation_selector = mo.ui.radio(
            options=list(_label_to_id),
            value=_id_to_label[_selected_id],
            label="Analysis evidence",
            on_change=lambda value: set_investigation_selection(
                (selected_investigation_group.group_id, _label_to_id[value])
            ),
        )
        investigation_label_to_id = _label_to_id
    return investigation_label_to_id, investigation_selector


@app.cell
def _(
    current_analysis_results,
    investigation_label_to_id,
    investigation_queue,
    investigation_selector,
):
    investigation_selected_id = (
        None
        if investigation_selector is None
        else investigation_label_to_id[investigation_selector.value]
    )
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
                    for result in current_analysis_results
                    if result.run.analysis_run_id == selected_investigation.analysis_run_id
                    and result.evidence.capability_id == selected_investigation.capability_id
                ),
                None,
            )
    return investigation_selected_id, selected_investigation, selected_investigation_result


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
    get_review_workflow,
    operations_actions,
    request_review_button,
    selected_investigation_result,
    set_review_request_error,
    set_review_request_success,
    set_review_workflow,
):
    if request_review_button is not None and request_review_button.value:
        try:
            if selected_investigation_result is None:
                raise ValueError("select an analysis result before requesting review")
            _, _updated_findings = operations_actions.request_review(selected_investigation_result)
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
    asset_names,
    OperationalAnalysisPresentationKind,
    investigation_asset_filter,
    investigation_capability_filter,
    investigation_group_count,
    investigation_group_selector,
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
    selected_investigation_group,
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

    if investigation_group_selector is None:
        _queue_panel = mo.vstack(
            [
                _filters,
                mo.md("### Queue\n\nNo saved analysis result matches the current filters."),
            ],
            gap=0.8,
        )
    else:
        _queue_blocks = [
            _filters,
            mo.md(
                f"### Queue\n\n"
                f"{investigation_group_count} group(s) · "
                f"{len(investigation_queue.items)} saved analyses"
            ),
            investigation_group_selector,
        ]
        if selected_investigation_group is not None and investigation_selector is not None:
            _queue_blocks.extend(
                [
                    mo.md(
                        f"#### Analysis evidence\n\n"
                        f"{selected_investigation_group.run_count} run(s) in this group"
                    ),
                    investigation_selector,
                ]
            )
        _queue_blocks.append(
            mo.md(
                "Groups combine the same asset, capability, and human-review state. "
                "Exact analysis evidence remains selectable inside each group. "
                "Order is newest evidence first, not severity."
            )
        )
        _queue_panel = mo.vstack(_queue_blocks, gap=0.8)

    if selected_investigation is None or selected_investigation_result is None:
        _detail_panel = mo.md(
            "## Investigation detail\n\nSelect an analysis result from the queue."
        )
    else:
        _presentation_kind = operational_analysis_presentation_kind(
            selected_investigation.capability_id
        )
        _evidence_blocks = [
            mo.Html(render_investigation_summary_html(selected_investigation, asset_names)),
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
                    mo.Html(
                        '<div class="phm-shell">'
                        + render_phase_unbalance_svg(selected_investigation_result)
                        + "</div>"
                    ),
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
        widths=[0.40, 0.60],
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
def _(FindingReviewStatus, asset_names, maintenance_queue, maintenance_status_label, mo):
    _status_labels = ["All", *[maintenance_status_label(status) for status in FindingReviewStatus]]
    maintenance_status_filter = mo.ui.dropdown(
        options=_status_labels,
        value="All",
        label="Status",
        full_width=True,
    )
    maintenance_asset_filter = mo.ui.dropdown(
        options={
            "All": "All",
            **{
                asset_names.option_label(asset_id): asset_id
                for asset_id in maintenance_queue.asset_ids
            },
        },
        value="All",
        label="Asset",
        full_width=True,
    )
    return maintenance_asset_filter, maintenance_status_filter


@app.cell
def _(
    FindingReviewStatus,
    asset_names,
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
        f"{maintenance_queue_label(item, asset_names)} · {index + 1}": item.finding_id
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
    else:
        maintenance_selector = None
    maintenance_filtered_count = len(_filtered)
    maintenance_label_to_id = _label_to_id
    return maintenance_filtered_count, maintenance_label_to_id, maintenance_selector


@app.cell
def _(maintenance_label_to_id, maintenance_queue, maintenance_selector):
    # A UI element's value can only be read outside the cell that created it.
    maintenance_selected_id = (
        None
        if maintenance_selector is None
        else maintenance_label_to_id[maintenance_selector.value]
    )
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
    return maintenance_selected_id, selected_maintenance


@app.cell
def _(
    OperationalAnalysisPresentationKind,
    current_analysis_results,
    investigation_queue,
    mo,
    operational_analysis_presentation_kind,
    phase_unbalance_summary_rows,
    selected_maintenance,
):
    # The review keeps references only; its evidence is read from the analysis result.
    maintenance_evidence = None
    maintenance_evidence_metrics = ()
    maintenance_open_investigation_button = None
    if selected_maintenance is not None:
        maintenance_evidence = next(
            (
                item
                for item in investigation_queue.items
                if item.finding_id == selected_maintenance.finding_id
            ),
            None,
        )
        _result = next(
            (
                item
                for item in current_analysis_results
                if item.run.analysis_run_id == selected_maintenance.analysis_run_id
            ),
            None,
        )
        if (
            _result is not None
            and operational_analysis_presentation_kind(selected_maintenance.capability_id)
            == OperationalAnalysisPresentationKind.PHASE_UNBALANCE
        ):
            maintenance_evidence_metrics = tuple(phase_unbalance_summary_rows(_result))
        if maintenance_evidence is not None:
            maintenance_open_investigation_button = mo.ui.run_button(
                label="Open evidence in Investigations"
            )
    return (
        maintenance_evidence,
        maintenance_evidence_metrics,
        maintenance_open_investigation_button,
    )


@app.cell
def _(
    investigation_queue,
    maintenance_open_investigation_button,
    resolve_finding_investigation_route,
    selected_maintenance,
    set_investigation_asset_filter,
    set_investigation_capability_filter,
    set_investigation_review_filter,
    set_investigation_selection,
    set_maintenance_error,
    set_navigation_page,
):
    if (
        maintenance_open_investigation_button is not None
        and maintenance_open_investigation_button.value
        and selected_maintenance is not None
    ):
        try:
            _route = resolve_finding_investigation_route(
                selected_maintenance.finding_id,
                investigation_queue=investigation_queue,
            )
        except LookupError as error:
            set_maintenance_error(str(error))
        else:
            set_investigation_review_filter("All")
            set_investigation_asset_filter("All")
            set_investigation_capability_filter("All")
            set_investigation_selection((_route.investigation_group_id, _route.investigation_id))
            set_navigation_page("Investigations")
    return


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
    get_review_workflow,
    investigation_findings,
    maintenance_ack_button,
    maintenance_add_note_button,
    maintenance_close_button,
    maintenance_note_input,
    operations_actions,
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
            _, _events = operations_actions.record_review_action(
                _finding,
                action=_action,
                note=_note,
            )
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
    asset_names,
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
    maintenance_evidence,
    maintenance_evidence_metrics,
    maintenance_open_investigation_button,
    render_maintenance_evidence_html,
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
        _evidence_blocks = [
            mo.Html(
                render_maintenance_evidence_html(
                    maintenance_evidence,
                    analysis_run_id=selected_maintenance.analysis_run_id,
                    metrics=maintenance_evidence_metrics,
                )
            )
        ]
        if maintenance_open_investigation_button is not None:
            _evidence_blocks.append(maintenance_open_investigation_button)
        _detail_panel = mo.vstack(
            [
                mo.Html(render_maintenance_summary_html(selected_maintenance, asset_names)),
                *_evidence_blocks,
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
    collection_service,
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
        collection_service=collection_service,
    )
    return (system_runtime,)


@app.cell
def _(
    asset_names,
    mo,
    render_system_diagnostics_html,
    render_system_errors_html,
    render_system_runtime_html,
    system_diagnostics,
    system_runtime,
):
    _name_conflicts = []
    if asset_names.conflicts:
        _rows = "\n".join(
            f"- `{asset_id}`: " + ", ".join(f"“{name}”" for name in names)
            for asset_id, names in asset_names.conflicts.items()
        )
        _name_conflicts.append(
            mo.callout(
                mo.md(
                    "Registered sources declare different display names for the same asset, "
                    "so the asset ID is shown instead:\n\n" + _rows
                ),
                kind="warn",
                title="Asset display name conflict",
            )
        )
    system_view = mo.vstack(
        [
            mo.Html(render_system_runtime_html(system_runtime)),
            mo.Html(render_system_errors_html(system_runtime)),
            *_name_conflicts,
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
    setup_clear_freshness_button,
    setup_enable_button,
    setup_error,
    setup_freshness_age_input,
    setup_pause_button,
    setup_run_diagnostic_button,
    setup_save_freshness_button,
    setup_section,
    setup_subscription_diagnostic_button,
    setup_selected_source,
    setup_source_selector,
    setup_start_collection_button,
    setup_stop_collection_button,
    setup_success,
    setup_diagnostic_error,
    setup_diagnostic_success,
    setup_workspace,
):
    _message_blocks = []
    if setup_error:
        _message_blocks.append(mo.callout(setup_error, kind="danger", title="Setup action failed"))
    if setup_success:
        _message_blocks.append(mo.callout(setup_success, kind="success", title="Setup updated"))

    if setup_selected_source is None:
        _selected_source_panel = mo.md(
            "### Connect your first data source\n\n"
            "Operations needs an observation source before it can show asset state or "
            "analysis evidence. Choose a prepared FILE source or a live OPC UA source below."
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
        _freshness_actions = [
            button
            for button in (
                setup_save_freshness_button,
                setup_clear_freshness_button,
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
                mo.accordion(
                    {
                        "Data age policy": mo.vstack(
                            [
                                setup_freshness_age_input,
                                mo.hstack(
                                    _freshness_actions,
                                    justify="start",
                                    gap=0.6,
                                ),
                                mo.md(
                                    "This policy compares the latest comparable observation "
                                    "time with the current assessment time. It does not prove "
                                    "connection health or asset health."
                                ),
                            ],
                            gap=0.6,
                        )
                    }
                ),
                mo.accordion(
                    {
                        "Advanced diagnostics": mo.vstack(
                            [
                                *(
                                    [
                                        mo.callout(
                                            setup_diagnostic_error,
                                            kind="danger",
                                            title="Diagnostic action failed",
                                        )
                                    ]
                                    if setup_diagnostic_error
                                    else []
                                ),
                                *(
                                    [
                                        mo.callout(
                                            setup_diagnostic_success,
                                            kind="success",
                                            title="Diagnostic action completed",
                                        )
                                    ]
                                    if setup_diagnostic_success
                                    else []
                                ),
                                mo.hstack(
                                    [
                                        button
                                        for button in (
                                            setup_run_diagnostic_button,
                                            setup_subscription_diagnostic_button,
                                        )
                                        if button is not None
                                    ],
                                    justify="start",
                                    gap=0.6,
                                ),
                                mo.md(
                                    "These bounded actions are for connection/data-contract "
                                    "diagnostics. They do not start the persistent collection "
                                    "service, and a successful attempt is not current connection "
                                    "health."
                                ),
                            ],
                            gap=0.6,
                        )
                    }
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
                    '<div class="phm-setup-help">Choose the prepared file boundary '
                    "and declare asset identity.</div>"
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
                    '<div class="phm-setup-help">Keep only discovered columns that '
                    "belong to this source mapping.</div>"
                    "</div>"
                ),
                _file_discovery_view,
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">3 · Define time & sampling</div>'
                    '<div class="phm-setup-help">FILE registration preserves column '
                    "identity; it does not infer physical measurement semantics.</div>"
                    "</div>"
                ),
                mo.hstack(
                    [file_timestamp_input, file_sampling_rate_input],
                    widths="equal",
                ),
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">4 · Review & save</div>'
                    '<div class="phm-setup-help">The file is validated before its '
                    "registration is persisted.</div>"
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
                "Connect & browse uses one bounded anonymous session to discover "
                "variable identity. "
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
                    '<div class="phm-setup-help">Declare endpoint and asset identity, '
                    "then run a bounded browse.</div>"
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
                    '<div class="phm-setup-help">Browse selection defines explicit '
                    "NodeId mapping. NodeId and BrowseName do not establish physical "
                    "meaning.</div>"
                    "</div>"
                ),
                (
                    opcua_signal_selection
                    if opcua_signal_selection is not None
                    else mo.md("No current browse result.")
                ),
                _mapping_view,
                mo.accordion({"Advanced explicit NodeId mapping": opcua_explicit_mapping_input}),
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">3 · Define meaning</div>'
                    '<div class="phm-setup-help">Meaning is explicit, versioned, and '
                    "evidence-backed. Leave channels unresolved when meaning is not "
                    "established.</div>"
                    "</div>"
                ),
                _semantic_editor,
                mo.Html(
                    '<div class="phm-setup-step">'
                    '<div class="phm-setup-step-title">4 · Review & save</div>'
                    '<div class="phm-setup-help">Saving registers configuration only. '
                    "It does not enable the source or start collection.</div>"
                    "</div>"
                ),
                register_setup_source_button,
            ],
            gap=0.75,
        )

    _add_source_surface = (
        _source_wizard
        if setup_selected_source is None
        else mo.accordion({"Add data source": _source_wizard})
    )
    _data_sources_view = mo.vstack(
        [
            mo.Html(render_setup_sources_html(setup_workspace)),
            _selected_source_panel,
            _add_source_surface,
        ],
        gap=1.0,
    )

    if setup_selected_source is None:
        _signal_mapping_view = mo.md("## Signal Mapping\n\nSelect or add a data source first.")
        _semantics_view = mo.md("## Measurement Semantics\n\nSelect or add a data source first.")
    else:
        _signal_mapping_view = mo.vstack(
            [
                setup_source_selector,
                mo.Html(render_setup_signals_html(setup_selected_source)),
                mo.md(
                    "Signal identity comes from declared FILE columns or explicit "
                    "OPC UA NodeId mapping. "
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
                    "Existing registrations are immutable evidence in the current "
                    "registry contract. "
                    "Measurement meaning is defined during registration; unresolved "
                    "channels stay unresolved "
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
                "The live three-phase runner and FILE analysis preserve their "
                "policy/version in evidence; "
                "this screen does not expose controls that the application contract "
                "cannot persist safely."
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
                        "Connect data sources, map signals, and record explicit "
                        "measurement meaning."
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
    asset_names,
    asset_selector,
    mo,
    monitor,
    monitor_attention_category,
    monitor_context_attention,
):
    if asset_selector is None:
        _context_attention = ()
    else:
        _context_attention = monitor_context_attention(
            monitor.attention,
            asset_id=asset_selector.value,
        )
    if _context_attention:
        attention_label_to_id = {
            (
                f"{monitor_attention_category(item)} · {item.title} · "
                f"{asset_names.label(item.asset_id) if item.asset_id else 'System'} · {index + 1}"
            ): item.attention_id
            for index, item in enumerate(_context_attention[:8])
        }
        attention_selector = mo.ui.dropdown(
            options=list(attention_label_to_id),
            value=next(iter(attention_label_to_id)),
            label="Attention",
            full_width=True,
        )
        attention_open_button = mo.ui.run_button(
            label="Open evidence",
            kind="warn",
        )
    else:
        attention_label_to_id = {}
        attention_selector = None
        attention_open_button = None
    return attention_label_to_id, attention_open_button, attention_selector


@app.cell
def _(attention_label_to_id, attention_selector, monitor):
    selected_attention = None
    if attention_selector is not None:
        _attention_id = attention_label_to_id[attention_selector.value]
        selected_attention = next(
            item for item in monitor.attention if item.attention_id == _attention_id
        )
    return (selected_attention,)


@app.cell
def _(
    investigation_queue,
    resolve_operations_attention_route,
    selected_attention,
):
    attention_route = None
    attention_route_error = ""
    if selected_attention is not None:
        try:
            attention_route = resolve_operations_attention_route(
                selected_attention,
                investigation_queue=investigation_queue,
            )
        except LookupError as error:
            attention_route_error = str(error)
    return attention_route, attention_route_error


@app.cell
def _(
    attention_open_button,
    attention_route,
    set_asset_section,
    set_asset_selection,
    set_investigation_asset_filter,
    set_investigation_capability_filter,
    set_investigation_review_filter,
    set_investigation_selection,
    set_navigation_page,
):
    if attention_open_button is not None and attention_open_button.value:
        if attention_route is None:
            pass
        elif attention_route.page == "Assets":
            set_asset_selection(attention_route.asset_id)
            set_asset_section(attention_route.asset_section)
            set_navigation_page("Assets")
        elif attention_route.page == "Investigations":
            set_investigation_review_filter("All")
            set_investigation_asset_filter("All")
            set_investigation_capability_filter("All")
            set_investigation_selection(
                (
                    attention_route.investigation_group_id,
                    attention_route.investigation_id,
                )
            )
            set_navigation_page("Investigations")
        else:
            set_navigation_page("System")
    return


@app.cell
def _(
    asset_names,
    attention_open_button,
    attention_route,
    attention_route_error,
    attention_selector,
    mo,
    monitor,
    monitor_attention_category,
    selected_attention,
    UTC,
):
    if selected_attention is None:
        attention_view = None
    else:
        _at = selected_attention.occurred_at
        if _at is None or _at.utcoffset() is None:
            _when = "Time unavailable"
        else:
            _age = (monitor.assessed_at - _at).total_seconds()
            if _age < -1:
                _relative = f"{abs(_age):.0f}s in future"
            elif _age < 1:
                _relative = "now"
            elif _age < 60:
                _relative = f"{_age:.0f}s ago"
            elif _age < 3600:
                _relative = f"{_age / 60:.1f}m ago"
            else:
                _relative = f"{_age / 3600:.1f}h ago"
            _when = f"{_relative} · {_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        _asset_label = (
            asset_names.label(selected_attention.asset_id)
            if selected_attention.asset_id
            else "System"
        )
        _category = monitor_attention_category(selected_attention)
        _metadata = f"**{_category}** · {_asset_label} · {_when}"
        _attention_kind = "danger" if selected_attention.status.value == "error" else "warn"
        _blocks = [
            mo.md("### Attention"),
            attention_selector,
            mo.md(_metadata),
            mo.callout(
                selected_attention.detail,
                kind=_attention_kind,
                title=selected_attention.title,
            ),
        ]
        if attention_route_error:
            _blocks.append(
                mo.callout(
                    attention_route_error,
                    kind="danger",
                    title="Drill-down unavailable",
                )
            )
        elif attention_open_button is not None:
            _blocks.append(attention_open_button)
        attention_view = mo.vstack(_blocks, gap=0.65)
    return (attention_view,)


@app.cell
def _(
    asset_analysis_view,
    asset_names,
    attention_view,
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
    monitor_evidence_view,
    monitor_signal_overview,
    monitor_signal_trends,
    navigation,
    operations_theme_css,
    refresh_button,
    render_asset_analysis_html,
    render_asset_events_html,
    render_asset_header_html,
    render_asset_maintenance_html,
    render_asset_overview_html,
    render_monitor_asset_context_html,
    setup_view,
    setup_workspace_css,
    signal_view,
    system_view,
    system_workspace_css,
):
    theme = mo.Html(
        operations_theme_css()
        + asset_workspace_css()
        + investigation_workspace_css()
        + maintenance_workspace_css()
        + system_workspace_css()
        + setup_workspace_css()
    )

    header = mo.hstack(
        [
            mo.md("# Operations\n\n설비의 현재 관측값과 시간 변화를 중심으로 확인합니다."),
            refresh_button,
        ],
        widths=[0.82, 0.18],
        align="start",
    )

    if asset_selector is None:
        monitor_view = mo.md(
            "## Monitor\n\n"
            "No asset evidence is available yet. Add a source in Setup or load history."
        )
    elif asset_workspace_error:
        monitor_view = mo.vstack(
            [
                asset_selector,
                mo.callout(
                    asset_workspace_error,
                    kind="danger",
                    title="Asset observation unavailable",
                ),
            ],
            gap=1.0,
        )
    elif asset_workspace is None:
        monitor_view = mo.vstack(
            [asset_selector, mo.md("Select an asset to observe its signals.")],
            gap=1.0,
        )
    else:
        _observation_view = mo.vstack(
            [
                asset_selector,
                mo.Html(
                    render_monitor_asset_context_html(
                        asset_workspace,
                        asset_names,
                        as_of=monitor.assessed_at,
                    )
                ),
                monitor_signal_overview,
                monitor_signal_trends,
                *([] if monitor_evidence_view is None else [monitor_evidence_view]),
                signal_view,
            ],
            gap=1.0,
        )
        if attention_view is None:
            monitor_view = _observation_view
        else:
            monitor_view = mo.hstack(
                [_observation_view, attention_view],
                widths=[0.72, 0.28],
                align="start",
                gap=1.2,
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
            "Analysis": asset_analysis_view,
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
                mo.Html(render_asset_header_html(asset_workspace, asset_names)),
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
        "Setup": setup_view,
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
