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
        setup_data_flow_confirmed,
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
        operational_analysis_presentation_kind,
        operations_error_css,
        operations_theme_css,
        render_analysis_quality_markdown,
        render_operations_recovery_html,
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
    from industrial_phm.presentation.operations_locale import (
        OperationsLocale,
        operations_messages,
        operations_page_label,
        operations_text,
        resolve_environment_operations_locale,
    )
    from industrial_phm.presentation.operations_maintenance import (
        maintenance_queue_label,
        maintenance_status_label,
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
        OperationsLocale,
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
        measurement_aggregation_rows,
        measurement_aggregation_summary,
        measurement_history_range_summary,
        measurement_history_rows,
        mo,
        monitor_attention_category,
        monitor_context_attention,
        operational_analysis_presentation_kind,
        operations_error_css,
        operations_messages,
        operations_page_label,
        operations_text,
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
        render_phase_unbalance_svg,
        render_operations_recovery_html,
        render_setup_signals_html,
        render_setup_source_detail_html,
        render_setup_sources_html,
        render_system_diagnostics_html,
        render_system_errors_html,
        render_system_runtime_html,
        resolve_environment_operations_locale,
        resolve_measurement_range,
        setup_data_flow_confirmed,
        setup_workspace_css,
        system_workspace_css,
    )


@app.cell
def _(mo):
    get_navigation_page, set_navigation_page = mo.state(None)
    return get_navigation_page, set_navigation_page


@app.cell
def _(OperationsLocale, mo, resolve_environment_operations_locale):
    _initial_locale = resolve_environment_operations_locale()
    locale_selector = mo.ui.dropdown(
        options={
            "한국어": OperationsLocale.KO_KR.value,
            "English": OperationsLocale.EN_US.value,
        },
        value=("한국어" if _initial_locale == OperationsLocale.KO_KR else "English"),
        label="Language / 언어",
    )
    return (locale_selector,)


@app.cell
def _(OperationsLocale, locale_selector):
    operations_locale = OperationsLocale(locale_selector.value)
    return (operations_locale,)


@app.cell
def _(mo):
    get_first_run_mode, set_first_run_mode = mo.state(None)
    get_first_run_sample, set_first_run_sample = mo.state(None)
    get_first_run_error, set_first_run_error = mo.state("")
    return (
        get_first_run_error,
        get_first_run_mode,
        get_first_run_sample,
        set_first_run_error,
        set_first_run_mode,
        set_first_run_sample,
    )


@app.cell
def _(get_monitor_revision, load_operations_app_context):
    _refresh = get_monitor_revision()
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
    navigation_page = get_navigation_page()
    if navigation_page is None:
        navigation_page = initial_operations_page(has_registered_sources=bool(registered_sources))
        set_navigation_page(navigation_page)
    return (navigation_page,)


@app.cell
def _(analysis_results, mo):
    get_analysis_results, set_analysis_results = mo.state(tuple(analysis_results))
    return get_analysis_results, set_analysis_results


@app.cell
def _(analysis_results, get_monitor_revision, set_analysis_results):
    if get_monitor_revision():
        set_analysis_results(tuple(analysis_results))
    return


@app.cell
def _(get_analysis_results):
    current_analysis_results = get_analysis_results()
    return (current_analysis_results,)


@app.cell
def _(OpcUaNodeMapping, operations_actions, operations_locale, operations_text):
    def parse_opcua_mapping_lines(value: str):
        mappings = []
        for line_number, raw_line in enumerate(value.splitlines(), start=1):
            _line = raw_line.strip()
            if not _line:
                continue
            if "," not in _line:
                raise ValueError(
                    operations_text("setup.mapping_line_format", operations_locale).format(
                        line_number=line_number
                    )
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
    get_monitor_revision,
    registered_sources,
    set_pending_semantics,
    set_setup_config,
    set_setup_error,
    set_setup_success,
):
    if get_monitor_revision():
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
        _setup_sources,
        _setup_lifecycles,
        _setup_collection,
        _setup_freshness,
    ) = get_setup_config()
    setup_error = get_setup_error()
    setup_success = get_setup_success()
    setup_workspace = build_setup_workspace(
        sources=_setup_sources,
        lifecycle_records=_setup_lifecycles,
        collection_records=_setup_collection,
        freshness_policies=_setup_freshness,
    )
    return (
        setup_error,
        setup_success,
        setup_workspace,
    )


@app.cell
def _(
    first_run_mode,
    mo,
    operations_locale,
    operations_text,
    setup_receipt_confirmed,
    setup_selected_source,
):
    first_run_sample_button = mo.ui.run_button(
        label=operations_text("first_run.sample.title", operations_locale),
        kind="success",
    )
    first_run_real_button = mo.ui.run_button(
        label=operations_text("first_run.real.open", operations_locale)
    )
    first_run_stop_sample_button = mo.ui.run_button(
        label=operations_text("first_run.sample.stop", operations_locale)
    )
    setup_refresh_data_flow_button = (
        None
        if setup_selected_source is None
        else mo.ui.run_button(label=operations_text("setup.refresh_data_flow", operations_locale))
    )
    setup_open_monitor_button = (
        None
        if setup_selected_source is None
        or (first_run_mode != "configured" and not setup_receipt_confirmed)
        else mo.ui.run_button(
            label=operations_text("setup.open_monitor", operations_locale),
            kind="success",
        )
    )
    return (
        first_run_real_button,
        first_run_sample_button,
        first_run_stop_sample_button,
        setup_open_monitor_button,
        setup_refresh_data_flow_button,
    )


@app.cell
def _(
    OperationsActionError,
    first_run_real_button,
    first_run_sample_button,
    first_run_stop_sample_button,
    operations_actions,
    set_first_run_error,
    set_first_run_mode,
    set_first_run_sample,
):
    if first_run_stop_sample_button.value:
        operations_actions.stop_first_run_sample()
        set_first_run_sample(None)
        set_first_run_error("")
        set_first_run_mode("landing")
    elif first_run_real_button.value:
        operations_actions.stop_first_run_sample()
        set_first_run_sample(None)
        set_first_run_error("")
        set_first_run_mode("real")
    elif first_run_sample_button.value:
        try:
            _launch = operations_actions.launch_first_run_sample()
        except OperationsActionError as error:
            set_first_run_sample(None)
            set_first_run_error(str(error))
            set_first_run_mode("landing")
        else:
            set_first_run_sample(_launch)
            set_first_run_error("")
            set_first_run_mode("sample")
    return


@app.cell
def _(
    get_first_run_error,
    get_first_run_mode,
    get_first_run_sample,
    registered_sources,
    set_first_run_mode,
):
    first_run_error = get_first_run_error()
    first_run_mode = get_first_run_mode()
    if first_run_mode is None:
        first_run_mode = "configured" if registered_sources else "landing"
        set_first_run_mode(first_run_mode)
    first_run_sample = get_first_run_sample()
    return first_run_error, first_run_mode, first_run_sample


@app.cell
def _(
    get_monitor_revision,
    set_monitor_revision,
    set_navigation_page,
    setup_open_monitor_button,
    setup_refresh_data_flow_button,
):
    if setup_refresh_data_flow_button is not None and setup_refresh_data_flow_button.value:
        set_monitor_revision(get_monitor_revision() + 1)
    elif setup_open_monitor_button is not None and setup_open_monitor_button.value:
        set_navigation_page("monitor")
    return


@app.cell
def _():
    setup_selection = {"source_id": None}
    return (setup_selection,)


@app.cell
def _(mo, operations_locale, operations_text, setup_selection, setup_workspace):
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
            label=operations_text("setup.source", operations_locale),
            full_width=True,
            on_change=lambda value: setup_selection.update(source_id=value),
        )
        setup_selected_source = next(
            item for item in setup_workspace.sources if item.source_id == _selected_source_id
        )
    else:
        setup_source_selector = None
        setup_selected_source = None
    return setup_selected_source, setup_source_selector


@app.cell
def _(overview, setup_data_flow_confirmed, setup_selected_source):
    if setup_selected_source is None:
        setup_selected_source_health = None
        setup_receipt_confirmed = False
    else:
        setup_selected_source_health = next(
            (
                item
                for item in overview.source_health_assessments
                if item.source_id == setup_selected_source.source_id
            ),
            None,
        )
        setup_receipt_confirmed = (
            False
            if setup_selected_source_health is None
            else setup_data_flow_confirmed(setup_selected_source_health)
        )
    return setup_receipt_confirmed, setup_selected_source_health


@app.cell
def _(SourceLifecycleState, mo, operations_locale, operations_text, setup_selected_source):
    setup_enable_button = None
    setup_pause_button = None
    if setup_selected_source is not None:
        if setup_selected_source.lifecycle_state == SourceLifecycleState.ACTIVE:
            setup_pause_button = mo.ui.run_button(
                label=operations_text("setup.pause", operations_locale)
            )
        else:
            setup_enable_button = mo.ui.run_button(
                label=operations_text("setup.enable", operations_locale),
                kind="success",
            )
    return setup_enable_button, setup_pause_button


@app.cell
def _(
    CollectionDesiredState,
    SourceType,
    mo,
    operations_locale,
    operations_text,
    setup_selected_source,
):
    setup_start_collection_button = None
    setup_stop_collection_button = None
    if setup_selected_source is not None and setup_selected_source.source_type == SourceType.OPCUA:
        if setup_selected_source.collection_desired_state == CollectionDesiredState.RUNNING:
            setup_stop_collection_button = mo.ui.run_button(
                label=operations_text("setup.stop_collection", operations_locale)
            )
        else:
            setup_start_collection_button = mo.ui.run_button(
                label=operations_text("setup.start_collection", operations_locale),
                kind="success",
            )
    return setup_start_collection_button, setup_stop_collection_button


@app.cell
def _(mo, operations_locale, operations_text, setup_selected_source):
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
            label=operations_text("setup.maximum_data_age", operations_locale),
            full_width=True,
        )
        setup_save_freshness_button = mo.ui.run_button(
            label=operations_text("setup.save_data_age", operations_locale)
        )
        setup_clear_freshness_button = (
            None
            if setup_selected_source.freshness_max_age_seconds is None
            else mo.ui.run_button(label=operations_text("setup.clear_policy", operations_locale))
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
    operations_locale,
    operations_text,
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
                raise ValueError(operations_text("setup.select_source_for_age", operations_locale))
            _source_id = setup_selected_source.source_id
            if _freshness_action == "save":
                if setup_freshness_age_input is None:
                    raise ValueError(
                        operations_text("setup.age_input_unavailable", operations_locale)
                    )
                _raw_value = setup_freshness_age_input.value.strip()
                if not _raw_value:
                    raise ValueError(
                        operations_text("setup.maximum_age_required", operations_locale)
                    )
                _policy, _state = operations_actions.set_freshness_policy(
                    _source_id,
                    max_observation_age_seconds=float(_raw_value),
                    changed_at=datetime.now().astimezone(),
                )
                if _policy is None:
                    raise AssertionError("saved freshness policy unexpectedly missing")
                _message = operations_text(
                    "setup.data_age_saved",
                    operations_locale,
                ).format(
                    source_id=_source_id,
                    seconds=_policy.max_observation_age_seconds,
                )
            else:
                _, _state = operations_actions.set_freshness_policy(
                    _source_id,
                    max_observation_age_seconds=None,
                    changed_at=datetime.now().astimezone(),
                )
                _message = operations_text(
                    "setup.data_age_cleared",
                    operations_locale,
                ).format(source_id=_source_id)
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
def _(SourceType, mo, operations_locale, operations_text, setup_selected_source):
    if setup_selected_source is None:
        setup_run_diagnostic_button = None
        setup_subscription_diagnostic_button = None
    else:
        setup_run_diagnostic_button = mo.ui.run_button(
            label=operations_text("setup.run_diagnostic", operations_locale)
        )
        setup_subscription_diagnostic_button = (
            mo.ui.run_button(label=operations_text("setup.collect_bounded", operations_locale))
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
    operations_locale,
    operations_text,
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
                raise ValueError(
                    operations_text("setup.select_source_for_diagnostic", operations_locale)
                )
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
                _message = operations_text(
                    (
                        "setup.diagnostic_cycle_completed"
                        if _diagnostic_kind == OperationsDiagnosticKind.CYCLE
                        else "setup.subscription_completed"
                    ),
                    operations_locale,
                )
                set_setup_diagnostic_error("")
                set_setup_diagnostic_success(
                    _message + operations_text("setup.refresh_runtime_hint", operations_locale)
                )
            elif _result.state == SourceRuntimeCycleState.SKIPPED:
                set_setup_diagnostic_success("")
                set_setup_diagnostic_error(
                    _result.message
                    or operations_text("setup.diagnostic_skipped", operations_locale)
                )
            else:
                _scope = "unknown" if _result.failure_scope is None else _result.failure_scope.value
                set_setup_diagnostic_success("")
                set_setup_diagnostic_error(
                    operations_text("setup.diagnostic_failure", operations_locale).format(
                        scope=_scope,
                        detail=(
                            _result.message
                            or operations_text(
                                "setup.diagnostic_failed_default",
                                operations_locale,
                            )
                        ),
                    )
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
    operations_locale,
    operations_text,
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
                raise ValueError(operations_text("setup.select_source_for_use", operations_locale))
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
            set_setup_success(
                operations_text("setup.source_use_changed", operations_locale).format(
                    source_id=_record.source_id,
                    state=_record.state.value,
                )
            )
    return


@app.cell
def _(
    CollectionDesiredState,
    datetime,
    get_setup_config,
    operations_actions,
    operations_locale,
    operations_text,
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
                raise ValueError(
                    operations_text("setup.select_opcua_for_collection", operations_locale)
                )
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
                operations_text("setup.collection_saved", operations_locale).format(
                    source_id=_record.source_id,
                    state=_record.desired_state.value,
                )
            )
    return


@app.cell
def _(SourceType, mo, operations_locale, operations_text):

    from html import escape

    class _AccessibleSetupText(mo.ui.text):
        """Retain the live input and expose its visible caption as a native label."""

        def __init__(self, *, accessible_label, **kwargs):
            self._accessible_label = accessible_label
            super().__init__(label="", **kwargs)

        @property
        def text(self):
            caption = escape(self._accessible_label)
            return (
                '<label class="phm-setup-accessible-field">'
                f'<span class="phm-setup-accessible-field-label">{caption}</span>'
                f"{super().text}</label>"
            )

    class _AccessibleSetupTextArea(mo.ui.text_area):
        """Apply the same native label association to the OPC UA mapping editor."""

        def __init__(self, *, accessible_label, **kwargs):
            self._accessible_label = accessible_label
            super().__init__(label="", **kwargs)

        @property
        def text(self):
            caption = escape(self._accessible_label)
            return (
                '<label class="phm-setup-accessible-field">'
                f'<span class="phm-setup-accessible-field-label">{caption}</span>'
                f"{super().text}</label>"
            )

    add_source_type = mo.ui.radio(
        options=["File", "OPC UA"],
        value="OPC UA",
        label=operations_text("setup.source_type", operations_locale),
    )
    add_source_id = _AccessibleSetupText(
        accessible_label=operations_text("setup.source_id", operations_locale),
        full_width=True,
    )
    add_source_name = _AccessibleSetupText(
        accessible_label=operations_text("setup.name", operations_locale),
        full_width=True,
    )
    add_asset_id = _AccessibleSetupText(
        accessible_label=operations_text("common.asset", operations_locale),
        full_width=True,
    )
    add_point_id = _AccessibleSetupText(
        accessible_label=operations_text("setup.measurement_point_optional", operations_locale),
        full_width=True,
    )

    file_path_input = _AccessibleSetupText(
        accessible_label=operations_text("setup.file_path", operations_locale),
        full_width=True,
    )
    file_mode_input = mo.ui.radio(
        options=["Snapshot", "History directory"],
        value="Snapshot",
        label=operations_text("setup.file_shape", operations_locale),
    )
    file_discover_button = mo.ui.run_button(
        label=operations_text("setup.discover_file", operations_locale)
    )
    file_timestamp_input = _AccessibleSetupText(
        value="timestamp",
        accessible_label=operations_text("setup.timestamp_column_optional", operations_locale),
        full_width=True,
    )
    file_sampling_rate_input = _AccessibleSetupText(
        value="",
        accessible_label=operations_text("setup.sampling_rate_optional", operations_locale),
        full_width=True,
    )

    opcua_endpoint_input = _AccessibleSetupText(
        accessible_label=operations_text("setup.endpoint", operations_locale),
        placeholder="opc.tcp://host:4840",
        full_width=True,
    )
    opcua_timeout_input = _AccessibleSetupText(
        value="4",
        accessible_label=operations_text("setup.timeout_seconds", operations_locale),
    )
    opcua_browse_button = mo.ui.run_button(
        label=operations_text("setup.connect_browse", operations_locale)
    )
    opcua_explicit_mapping_input = _AccessibleSetupTextArea(
        value="",
        accessible_label=operations_text("setup.advanced_mapping", operations_locale),
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
    operations_locale,
    operations_text,
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
            set_setup_success(operations_text("setup.file_discovery_completed", operations_locale))
    return


@app.cell
def _(
    get_file_discovery,
    get_file_discovery_signature,
    file_mode_input,
    file_path_input,
    mo,
    operations_locale,
    operations_text,
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
            label=operations_text("setup.signals_to_keep", operations_locale),
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
    operations_locale,
    operations_text,
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
            set_setup_success(operations_text("setup.browse_completed_identity", operations_locale))
    return


@app.cell
def _(
    get_opcua_browse,
    get_opcua_browse_signature,
    mo,
    opcua_endpoint_input,
    operations_locale,
    operations_text,
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
            label=operations_text("setup.signals_to_keep", operations_locale),
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
def _(mo, opcua_candidate_mappings, operations_locale, operations_text):
    _semantic_channels = [item.channel_id for item in opcua_candidate_mappings]
    if _semantic_channels:
        semantic_channel_input = mo.ui.dropdown(
            options=_semantic_channels,
            value=_semantic_channels[0],
            label=operations_text("common.signal", operations_locale),
            full_width=True,
        )
        semantic_observed_property_input = mo.ui.text(
            label=operations_text("setup.observed_property", operations_locale),
            full_width=True,
        )
        semantic_scope_input = mo.ui.text(
            label=operations_text("setup.scope_optional", operations_locale),
            full_width=True,
        )
        semantic_statistic_input = mo.ui.text(
            label=operations_text("setup.statistic_optional", operations_locale),
            full_width=True,
        )
        semantic_unit_input = mo.ui.text(
            label=operations_text("setup.unit_optional", operations_locale),
            full_width=True,
        )
        semantic_unit_evidence_input = mo.ui.text(
            label=operations_text("setup.unit_evidence", operations_locale),
            full_width=True,
        )
        semantic_version_input = mo.ui.text(
            label=operations_text("setup.semantic_version", operations_locale),
            full_width=True,
        )
        semantic_evidence_input = mo.ui.text(
            label=operations_text("setup.interpretation_evidence", operations_locale),
            full_width=True,
        )
        semantic_save_button = mo.ui.run_button(
            label=operations_text("setup.save_meaning", operations_locale)
        )
        semantic_clear_button = mo.ui.run_button(
            label=operations_text("setup.keep_unresolved", operations_locale)
        )
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
    operations_locale,
    operations_text,
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
                raise ValueError(operations_text("setup.select_mapping_first", operations_locale))
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
                raise ValueError(
                    operations_text("setup.explicit_meaning_required", operations_locale)
                )
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
            set_setup_success(
                operations_text("setup.meaning_saved", operations_locale).format(
                    channel_id=_channel_id
                )
            )
    elif (
        semantic_clear_button is not None
        and semantic_clear_button.value
        and semantic_channel_input is not None
    ):
        _current = dict(get_pending_semantics())
        _current.pop(semantic_channel_input.value, None)
        set_pending_semantics(_current)
        set_setup_error("")
        set_setup_success(
            operations_text("setup.remain_unresolved", operations_locale).format(
                channel_id=semantic_channel_input.value
            )
        )
    return


@app.cell
def _(get_pending_semantics):
    pending_semantics = get_pending_semantics()
    return (pending_semantics,)


@app.cell
def _(mo, operations_locale, operations_text):
    register_setup_source_button = mo.ui.run_button(
        label=operations_text("setup.review_save_source", operations_locale),
        kind="success",
    )
    return (register_setup_source_button,)


@app.cell
def _(mo):
    # A run button can remain truthy during reactive state updates after a click.
    # Consume its click once so a successful registration is not retried.
    get_setup_source_click_consumed, set_setup_source_click_consumed = mo.state(False)
    return get_setup_source_click_consumed, set_setup_source_click_consumed


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
    get_setup_source_click_consumed,
    operations_actions,
    opcua_candidate_mappings,
    opcua_endpoint_input,
    opcua_mapping_error,
    opcua_timeout_input,
    operations_locale,
    operations_text,
    pending_semantics,
    register_setup_source_button,
    set_pending_semantics,
    set_setup_config,
    set_setup_error,
    set_setup_source_click_consumed,
    set_setup_success,
):
    if not register_setup_source_button.value:
        if get_setup_source_click_consumed():
            set_setup_source_click_consumed(False)
    elif not get_setup_source_click_consumed():
        set_setup_source_click_consumed(True)
        try:
            _source_id = add_source_id.value.strip()
            if add_source_type.value == "File":
                if not file_discovery_current or file_discovery is None:
                    raise ValueError(
                        operations_text("setup.discover_before_save", operations_locale)
                    )
                _signals = tuple(
                    () if file_signal_selection is None else file_signal_selection.value
                )
                if not _signals:
                    raise ValueError(operations_text("setup.select_file_signal", operations_locale))
                _common = set(file_discovery.common_columns)
                _timestamp = file_timestamp_input.value.strip() or None
                if _timestamp is not None and _timestamp not in _common:
                    raise ValueError(
                        operations_text("setup.timestamp_not_discovered", operations_locale)
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
            else:
                if opcua_mapping_error:
                    raise ValueError(opcua_mapping_error)
                if not opcua_candidate_mappings:
                    raise ValueError(
                        operations_text("setup.select_opcua_signal", operations_locale)
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
            set_setup_success(
                operations_text("setup.source_saved", operations_locale).format(
                    source_id=_candidate.source_id
                )
            )
    return


@app.cell
def _(mo):
    get_asset_selection, set_asset_selection = mo.state(None)
    get_asset_section, set_asset_section = mo.state("overview")
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
    operations_locale,
    operations_text,
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
            label=operations_text("common.asset", operations_locale),
            full_width=True,
            on_change=set_asset_selection,
        )
    else:
        asset_selector = None
    _asset_sections = {
        operations_text("asset.section.overview", operations_locale): "overview",
        operations_text("asset.section.signals", operations_locale): "signals",
        operations_text("asset.section.analysis", operations_locale): "analysis",
        operations_text("asset.section.events", operations_locale): "events",
        operations_text("asset.section.maintenance", operations_locale): "maintenance",
    }
    _requested_section = get_asset_section()
    _section_label_by_id = {value: label for label, value in _asset_sections.items()}
    asset_section = mo.ui.radio(
        options=_asset_sections,
        value=_section_label_by_id.get(
            _requested_section,
            operations_text("asset.section.overview", operations_locale),
        ),
        label=operations_text("asset.view", operations_locale),
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
    navigation_page,
    overview,
    registered_sources,
    skipped_analysis_attempts,
):
    asset_workspace = None
    asset_workspace_error = None
    asset_history_error = None
    if navigation_page in {"assets", "monitor"} and asset_selector is not None:
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
def _(
    FileSourceConfig,
    FileSourceMode,
    asset_workspace,
    mo,
    operations_locale,
    operations_text,
    registered_sources,
):
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
                label=operations_text("asset.file_snapshot_source", operations_locale),
                full_width=True,
            )
            asset_run_file_analysis_button = mo.ui.run_button(
                label=operations_text("asset.analyze_file_snapshot", operations_locale),
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
    operations_locale,
    operations_text,
    registered_sources,
    set_analysis_results,
    set_asset_analysis_action_error,
    set_asset_analysis_action_success,
):
    if asset_run_file_analysis_button is not None and asset_run_file_analysis_button.value:
        try:
            if asset_file_analysis_source is None:
                raise ValueError(
                    operations_text("asset.select_file_before_analysis", operations_locale)
                )
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
                operations_text("asset.file_analysis_success", operations_locale)
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
    operations_locale,
    operations_text,
    render_asset_analysis_html,
    render_operations_recovery_html,
):
    if asset_workspace is None:
        asset_analysis_view = mo.md(operations_text("asset.no_selection", operations_locale))
    else:
        _blocks = [mo.Html(render_asset_analysis_html(asset_workspace, operations_locale))]
        if asset_analysis_action_error:
            _blocks.append(
                mo.Html(
                    render_operations_recovery_html(
                        "asset.analysis",
                        technical_detail=asset_analysis_action_error,
                        locale=operations_locale,
                    )
                )
            )
        if asset_analysis_action_success:
            _blocks.append(
                mo.callout(
                    asset_analysis_action_success,
                    kind="success",
                    title=operations_text("asset.analysis_recorded", operations_locale),
                )
            )
        if asset_file_analysis_source is not None and asset_run_file_analysis_button is not None:
            _blocks.extend(
                [
                    mo.md(
                        "### " + operations_text("asset.analyze_prepared_file", operations_locale)
                    ),
                    asset_file_analysis_source,
                    asset_run_file_analysis_button,
                    mo.md(operations_text("asset.file_analysis_help", operations_locale)),
                ]
            )
        else:
            _blocks.append(mo.md(operations_text("asset.no_file_snapshot", operations_locale)))
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
    operations_locale,
    operations_text,
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
                label=operations_text("common.signal", operations_locale),
                full_width=True,
                on_change=set_signal_channel_choice,
            )
        else:
            signal_channel_selector = None
    signal_range_selector = mo.ui.radio(
        options=["Live", "15m", "24h", "7d"],
        value="Live",
        label=operations_text("common.time_range", operations_locale),
    )
    return signal_channel_selector, signal_range_selector


@app.cell
def _(mo):
    get_monitor_range, set_monitor_range = mo.state("1h")
    get_monitor_revision, set_monitor_revision = mo.state(0)
    return get_monitor_range, set_monitor_range, get_monitor_revision, set_monitor_revision


@app.cell
def _(get_monitor_range):
    monitor_range_id = get_monitor_range()
    return (monitor_range_id,)


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
    navigation_page,
    query_operations_latest_asset_measurements,
):
    monitor_latest_points = ()
    monitor_latest_rows = ()
    monitor_latest_error = ""
    if navigation_page == "monitor" and asset_selector is not None and history_reader is not None:
        try:
            monitor_latest_points = query_operations_latest_asset_measurements(
                history_reader,
                asset_selector.value,
                limit=1000,
            )
            monitor_latest_rows = tuple(
                latest_measurement_rows(monitor_latest_points, as_of=assessed_at)
            )
        except OperationsReadError as error:
            monitor_latest_error = str(error)
    return monitor_latest_points, monitor_latest_rows, monitor_latest_error


@app.cell
def _(mo):
    get_monitor_comparisons, set_monitor_comparisons = mo.state({})
    return get_monitor_comparisons, set_monitor_comparisons


@app.cell
def _(
    asset_selector,
    get_monitor_comparisons,
    monitor_latest_rows,
    registered_sources,
    signal_channel_selector,
):
    from industrial_phm.presentation.monitor_workspace import (
        comparison_channels,
    )
    from industrial_phm.presentation.monitor_workspace import (
        signal_payload as _signal_payload,
    )

    _focus = None if signal_channel_selector is None else signal_channel_selector.value
    _asset = None if asset_selector is None else asset_selector.value
    monitor_comparison_channels = comparison_channels(
        _signal_payload(monitor_latest_rows, registered_sources, _asset),
        _focus,
        get_monitor_comparisons().get(_asset),
    )
    return (monitor_comparison_channels,)


@app.cell
def _(
    OperationsReadError,
    asset_selector,
    history_reader,
    investigation_queue,
    monitor_latest_points,
    monitor_comparison_channels,
    monitor_range_id,
    navigation_page,
    query_operations_multi_signal_measurement_aggregation,
    resolve_measurement_range,
    signal_channel_selector,
):
    monitor_chart_data = None
    monitor_chart_error = ""
    monitor_window_evidence_items = ()
    if navigation_page == "monitor" and asset_selector is not None and history_reader is not None:
        _event_times = tuple(
            point.measurement.event_at
            for point in monitor_latest_points
            if point.measurement.event_at is not None
        )
        _selected_channel = (
            None if signal_channel_selector is None else signal_channel_selector.value
        )
        _comparison_channels = monitor_comparison_channels
        _channels = tuple(
            dict.fromkeys(
                (() if _selected_channel is None else (_selected_channel,)) + _comparison_channels
            )
        )[:6]
        if _event_times and _channels:
            _anchor_at = max(_event_times)
            _range_id = monitor_range_id
            _start_at, _end_at = resolve_measurement_range(
                _range_id,
                as_of=_anchor_at,
                start_at=_anchor_at,
                end_at=_anchor_at,
            )
            monitor_window_evidence_items = tuple(
                item
                for item in investigation_queue.items
                if item.asset_id == asset_selector.value
                and item.observed_end_at >= _start_at
                and item.observed_start_at <= _end_at
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
                monitor_chart_error = str(error)
            else:
                monitor_chart_data = _multi_signal
    return (
        monitor_chart_data,
        monitor_chart_error,
        monitor_window_evidence_items,
    )


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
    navigation_page,
    operations_context,
    operations_locale,
    operations_text,
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
    if navigation_page != "assets" or asset_section.value != "signals":
        signal_view = mo.md("")
    elif asset_workspace is None:
        signal_view = mo.md(operations_text("asset.no_selection", operations_locale))
    elif asset_history_error:
        signal_view = mo.callout(
            asset_history_error,
            kind="danger",
            title=operations_text("asset.history_unavailable", operations_locale),
        )
    elif signal_channel_selector is None:
        signal_view = mo.md(
            "### "
            + operations_text("asset.section.signals", operations_locale)
            + "\n\n"
            + operations_text("asset.no_signal", operations_locale)
        )
    elif asset_selector is None:
        signal_view = mo.md(
            "### "
            + operations_text("asset.section.signals", operations_locale)
            + "\n\n"
            + operations_text("asset.no_selection", operations_locale)
        )
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
                    mo.md(
                        "#### " + operations_text("asset.recent_event_points", operations_locale)
                    ),
                ]
                if _live_page.points:
                    _live_blocks.extend(
                        [
                            mo.Html(
                                '<div class="phm-chart-workspace">'
                                + render_measurement_history_svg(_live_page)
                                + "</div>"
                            ),
                            mo.accordion(
                                {
                                    operations_text(
                                        "asset.raw_observations", operations_locale
                                    ): mo.ui.table(
                                        measurement_history_rows(_live_page),
                                        page_size=10,
                                    )
                                }
                            ),
                        ]
                    )
                else:
                    _live_blocks.append(
                        mo.md(operations_text("asset.no_recent_persisted", operations_locale))
                    )
                _live_blocks.append(
                    mo.md(operations_text("asset.live_evidence_help", operations_locale))
                )
                signal_view = mo.vstack(_live_blocks, gap=1.0)
            elif history_reader is None:
                signal_view = mo.md(
                    "### "
                    + operations_text("asset.section.signals", operations_locale)
                    + "\n\n"
                    + operations_text("asset.no_history_catalog", operations_locale)
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
                        mo.md(
                            "#### "
                            + operations_text("asset.latest_stored_value", operations_locale)
                        ),
                        mo.ui.table(
                            [
                                {
                                    operations_text("common.source", operations_locale): row[
                                        "source"
                                    ],
                                    operations_text("common.point", operations_locale): row[
                                        "measurement_point"
                                    ],
                                    operations_text("common.time", operations_locale): row["time"],
                                    operations_text("common.value", operations_locale): row[
                                        "value"
                                    ],
                                    operations_text("common.unit", operations_locale): row["unit"],
                                    operations_text("common.quality", operations_locale): row[
                                        "quality"
                                    ],
                                    operations_text(
                                        "common.source_quality", operations_locale
                                    ): row["source_quality"],
                                    operations_text("common.time_state", operations_locale): row[
                                        "event_time_state"
                                    ],
                                    operations_text(
                                        "common.history_age_seconds", operations_locale
                                    ): row["history_age_seconds"],
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
                            mo.Html(
                                '<div class="phm-chart-workspace">'
                                + render_measurement_aggregation_svg(_aggregation)
                                + "</div>"
                            ),
                            mo.ui.table(
                                [measurement_aggregation_summary(_aggregation)],
                                selection=None,
                            ),
                            mo.accordion(
                                {
                                    operations_text(
                                        "asset.data_details", operations_locale
                                    ): mo.ui.table(
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
                                '<div class="phm-chart-workspace">'
                                + render_measurement_history_svg(
                                    _page,
                                    start_at=_start_at,
                                    end_at=_end_at,
                                )
                                + "</div>"
                            )
                        )
                        _trend_blocks.append(
                            mo.accordion(
                                {
                                    operations_text(
                                        "asset.raw_observations", operations_locale
                                    ): mo.ui.table(
                                        measurement_history_rows(_page),
                                        page_size=10,
                                    )
                                }
                            )
                        )
                    else:
                        _trend_blocks.append(
                            mo.md(operations_text("asset.no_observation_range", operations_locale))
                        )
                    _trend_view = mo.vstack(_trend_blocks, gap=0.8)

                signal_view = mo.vstack(
                    [
                        _controls,
                        _latest_view,
                        _trend_view,
                        mo.md(operations_text("asset.stored_evidence_help", operations_locale)),
                    ],
                    gap=1.0,
                )
        except OperationsReadError as error:
            signal_view = mo.callout(
                str(error),
                kind="danger",
                title=operations_text("asset.signals_unavailable", operations_locale),
            )
    return (signal_view,)


@app.cell
def _(mo):
    get_investigation_selection, set_investigation_selection = mo.state((None, None))
    get_investigation_review_filter, set_investigation_review_filter = mo.state("all")
    get_investigation_asset_filter, set_investigation_asset_filter = mo.state("all")
    get_investigation_capability_filter, set_investigation_capability_filter = mo.state("all")
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
    get_monitor_revision,
    review_events,
    set_review_request_error,
    set_review_request_success,
    set_review_workflow,
):
    if get_monitor_revision():
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
    operations_locale,
    operations_text,
    set_investigation_asset_filter,
    set_investigation_capability_filter,
    set_investigation_review_filter,
):
    _all_label = operations_text("common.all", operations_locale)

    _review_labels = {
        investigation_review_label(state, operations_locale): state.value
        for state in InvestigationReviewState
    }
    _review_value = get_investigation_review_filter()
    _review_label_by_value = {value: label for label, value in _review_labels.items()}
    investigation_review_filter = mo.ui.dropdown(
        options={_all_label: "all", **_review_labels},
        value=_review_label_by_value.get(_review_value, _all_label),
        label=operations_text("common.review", operations_locale),
        full_width=True,
        on_change=set_investigation_review_filter,
    )

    _asset_options = {
        _all_label: "all",
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
            else _all_label
        ),
        label=operations_text("common.asset", operations_locale),
        full_width=True,
        on_change=set_investigation_asset_filter,
    )

    _capability_labels = {
        investigation_capability_label(capability_id, operations_locale): capability_id
        for capability_id in investigation_queue.capability_ids
    }
    _capability_label_by_id = {value: label for label, value in _capability_labels.items()}
    _capability_value = get_investigation_capability_filter()
    investigation_capability_filter = mo.ui.dropdown(
        options={_all_label: "all", **_capability_labels},
        value=_capability_label_by_id.get(_capability_value, _all_label),
        label=operations_text("common.capability", operations_locale),
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
    operations_locale,
    operations_text,
    set_investigation_selection,
):
    _review_state = (
        None
        if investigation_review_filter.value == "all"
        else InvestigationReviewState(investigation_review_filter.value)
    )
    _groups = investigation_queue.groups(
        review_state=_review_state,
        asset_id=(
            None if investigation_asset_filter.value == "all" else investigation_asset_filter.value
        ),
        capability_id=(
            None
            if investigation_capability_filter.value == "all"
            else investigation_capability_filter.value
        ),
    )
    _group_label_to_id = {
        (
            f"{investigation_group_option_label(group, asset_names, operations_locale)} "
            f"· {index + 1}"
        ): group.group_id
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
            label=operations_text("common.queue_groups", operations_locale),
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
    operations_locale,
    operations_text,
    selected_investigation_group,
    set_investigation_selection,
):
    if selected_investigation_group is None:
        investigation_selector = None
        investigation_label_to_id = {}
    else:
        _label_to_id = {
            (
                f"{investigation_queue_option_label(item, asset_names, operations_locale)} "
                f"· {index + 1}"
            ): (item.investigation_id)
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
            label=operations_text("common.analysis_evidence", operations_locale),
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
def _(
    InvestigationReviewState,
    mo,
    operations_locale,
    operations_text,
    selected_investigation,
):
    if (
        selected_investigation is not None
        and selected_investigation.review_state == InvestigationReviewState.NOT_REQUESTED
    ):
        request_review_button = mo.ui.run_button(
            label=operations_text("investigation.request_review", operations_locale),
            kind="warn",
        )
    else:
        request_review_button = None
    return (request_review_button,)


@app.cell
def _(
    get_review_workflow,
    operations_actions,
    operations_locale,
    operations_text,
    request_review_button,
    selected_investigation_result,
    set_review_request_error,
    set_review_request_success,
    set_review_workflow,
):
    if request_review_button is not None and request_review_button.value:
        try:
            if selected_investigation_result is None:
                raise ValueError(
                    operations_text("investigation.select_result_for_review", operations_locale)
                )
            _, _updated_findings = operations_actions.request_review(selected_investigation_result)
        except (OSError, ValueError) as error:
            set_review_request_error(str(error))
            set_review_request_success("")
        else:
            _, _current_events = get_review_workflow()
            set_review_workflow((_updated_findings, _current_events))
            set_review_request_error("")
            set_review_request_success(
                operations_text("investigation.review_requested_detail", operations_locale)
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
    operations_locale,
    operations_text,
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
    render_operations_recovery_html,
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
                mo.md(
                    "### "
                    + operations_text("investigation.queue", operations_locale)
                    + "\n\n"
                    + operations_text("investigation.no_filter_match", operations_locale)
                ),
            ],
            gap=0.8,
        )
    else:
        _queue_blocks = [
            _filters,
            mo.md(
                "### "
                + operations_text("investigation.queue", operations_locale)
                + "\n\n"
                + operations_text("investigation.queue_summary", operations_locale).format(
                    groups=investigation_group_count,
                    analyses=len(investigation_queue.items),
                )
            ),
            investigation_group_selector,
        ]
        if selected_investigation_group is not None and investigation_selector is not None:
            _queue_blocks.extend(
                [
                    mo.md(
                        "#### "
                        + operations_text(
                            "investigation.evidence_heading",
                            operations_locale,
                        )
                        + "\n\n"
                        + operations_text(
                            "investigation.group_run_count",
                            operations_locale,
                        ).format(runs=selected_investigation_group.run_count)
                    ),
                    investigation_selector,
                ]
            )
        _queue_blocks.append(
            mo.md(operations_text("investigation.grouping_help", operations_locale))
        )
        _queue_panel = mo.vstack(_queue_blocks, gap=0.8)

    if selected_investigation is None or selected_investigation_result is None:
        _detail_panel = mo.md(
            "## "
            + operations_text("investigation.title", operations_locale)
            + "\n\n"
            + operations_text("investigation.select_detail", operations_locale)
        )
    else:
        _presentation_kind = operational_analysis_presentation_kind(
            selected_investigation.capability_id
        )
        _evidence_blocks = [
            mo.Html(
                render_investigation_summary_html(
                    selected_investigation,
                    asset_names,
                    operations_locale,
                )
            ),
            mo.md(render_analysis_quality_markdown(selected_investigation_result.run)),
        ]

        if _presentation_kind == OperationalAnalysisPresentationKind.PHASE_UNBALANCE:
            _evidence_blocks.extend(
                [
                    mo.md(
                        "### "
                        + operations_text("investigation.evidence_summary", operations_locale)
                    ),
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
                            operations_text(
                                "investigation.excluded_observations",
                                operations_locale,
                            ): mo.ui.table(
                                phase_unbalance_exclusion_rows(selected_investigation_result),
                                selection=None,
                                page_size=12,
                            ),
                            operations_text(
                                "investigation.evidence_provenance",
                                operations_locale,
                            ): mo.ui.table(
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
                {
                    operations_text("investigation.feature", operations_locale): name,
                    operations_text("investigation.value", operations_locale): value,
                }
                for name, value in zip(
                    _evidence.feature_names,
                    _evidence.values,
                    strict=True,
                )
            ]
            _evidence_blocks.extend(
                [
                    mo.md(
                        "### "
                        + operations_text(
                            "investigation.vibration_evidence",
                            operations_locale,
                        )
                    ),
                    mo.ui.table(_feature_rows, selection=None),
                    mo.md(operations_text("investigation.vibration_help", operations_locale)),
                ]
            )
        else:
            _evidence_blocks.append(
                mo.callout(
                    operations_text("investigation.renderer_detail", operations_locale),
                    kind="neutral",
                    title=operations_text(
                        "investigation.renderer_unavailable",
                        operations_locale,
                    ),
                )
            )

        _review_blocks = []
        if review_request_error:
            _review_blocks.append(
                mo.Html(
                    render_operations_recovery_html(
                        "investigation.review",
                        technical_detail=review_request_error,
                        locale=operations_locale,
                    )
                )
            )
        if review_request_success:
            _review_blocks.append(
                mo.callout(
                    review_request_success,
                    kind="success",
                    title=operations_text("investigation.review_requested", operations_locale),
                )
            )
        if request_review_button is not None:
            _review_blocks.extend(
                [
                    mo.md(
                        "### " + operations_text("investigation.human_review", operations_locale)
                    ),
                    request_review_button,
                    mo.md(operations_text("investigation.review_help", operations_locale)),
                ]
            )
        else:
            _review_blocks.append(
                mo.md(
                    "### "
                    + operations_text("investigation.human_review", operations_locale)
                    + "\n\n"
                    + operations_text(
                        "investigation.current_review_state",
                        operations_locale,
                    ).format(
                        state=investigation_review_label(
                            selected_investigation.review_state,
                            operations_locale,
                        )
                    )
                )
            )

        _detail_panel = mo.vstack(
            [
                *_evidence_blocks,
                *_review_blocks,
                mo.accordion(
                    {
                        operations_text(
                            "investigation.evidence_identity",
                            operations_locale,
                        ): mo.Html(
                            render_investigation_evidence_identity_html(
                                selected_investigation,
                                operations_locale,
                            )
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
def _(
    FindingReviewStatus,
    asset_names,
    maintenance_queue,
    maintenance_status_label,
    mo,
    operations_locale,
    operations_text,
):
    _all_label = operations_text("common.all", operations_locale)
    _status_labels = {
        maintenance_status_label(status, operations_locale): status.value
        for status in FindingReviewStatus
    }
    maintenance_status_filter = mo.ui.dropdown(
        options={_all_label: "all", **_status_labels},
        value=_all_label,
        label=operations_text("common.status", operations_locale),
        full_width=True,
    )
    maintenance_asset_filter = mo.ui.dropdown(
        options={
            _all_label: "all",
            **{
                asset_names.option_label(asset_id): asset_id
                for asset_id in maintenance_queue.asset_ids
            },
        },
        value=_all_label,
        label=operations_text("common.asset", operations_locale),
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
    mo,
    operations_locale,
    operations_text,
):
    _filtered = maintenance_queue.filter(
        status=(
            None
            if maintenance_status_filter.value == "all"
            else FindingReviewStatus(maintenance_status_filter.value)
        ),
        asset_id=(
            None if maintenance_asset_filter.value == "all" else maintenance_asset_filter.value
        ),
    )
    _label_to_id = {
        (
            f"{maintenance_queue_label(item, asset_names, operations_locale)} · {index + 1}"
        ): item.finding_id
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
            label=operations_text("common.queue", operations_locale),
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
    operations_locale,
    operations_text,
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
                label=operations_text("maintenance.open_evidence", operations_locale)
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
            set_investigation_review_filter("all")
            set_investigation_asset_filter("all")
            set_investigation_capability_filter("all")
            set_investigation_selection((_route.investigation_group_id, _route.investigation_id))
            set_navigation_page("investigations")
    return


@app.cell
def _(
    FindingReviewStatus,
    mo,
    operations_locale,
    operations_text,
    selected_maintenance,
):
    if selected_maintenance is None or selected_maintenance.status == FindingReviewStatus.CLOSED:
        maintenance_note_input = None
        maintenance_add_note_button = None
        maintenance_ack_button = None
        maintenance_close_button = None
    else:
        maintenance_note_input = mo.ui.text_area(
            value="",
            label=operations_text("maintenance.review_note", operations_locale),
            rows=3,
            full_width=True,
        )
        maintenance_add_note_button = mo.ui.run_button(
            label=operations_text("maintenance.add_note", operations_locale)
        )
        maintenance_ack_button = (
            mo.ui.run_button(
                label=operations_text("maintenance.acknowledge", operations_locale),
                kind="success",
            )
            if selected_maintenance.status == FindingReviewStatus.OPEN
            else None
        )
        maintenance_close_button = (
            mo.ui.run_button(
                label=operations_text("maintenance.close_review", operations_locale),
                kind="warn",
            )
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
    operations_locale,
    operations_text,
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
                raise ValueError(
                    operations_text("maintenance.select_before_action", operations_locale)
                )
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
            set_maintenance_success(
                operations_text("maintenance.action_recorded", operations_locale).format(
                    action=_action.value
                )
            )
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
    mo,
    operations_locale,
    operations_text,
    maintenance_evidence,
    maintenance_evidence_metrics,
    maintenance_open_investigation_button,
    render_maintenance_evidence_html,
    render_maintenance_identity_html,
    render_maintenance_summary_html,
    render_maintenance_timeline_html,
    selected_maintenance,
    render_operations_recovery_html,
):
    _counts = mo.md(
        "### "
        + operations_text("maintenance.workload", operations_locale)
        + "\n\n"
        + operations_text("maintenance.counts", operations_locale).format(
            open=maintenance_queue.count(FindingReviewStatus.OPEN),
            acknowledged=maintenance_queue.count(FindingReviewStatus.ACKNOWLEDGED),
            closed=maintenance_queue.count(FindingReviewStatus.CLOSED),
        )
    )
    _filters = mo.hstack(
        [maintenance_status_filter, maintenance_asset_filter],
        widths=[0.45, 0.55],
        align="start",
    )
    if maintenance_selector is None:
        _queue_panel = mo.vstack(
            [
                _counts,
                _filters,
                mo.md(operations_text("maintenance.no_filter_match", operations_locale)),
            ],
            gap=0.8,
        )
    else:
        _queue_panel = mo.vstack(
            [
                _counts,
                _filters,
                mo.md(
                    "### "
                    + operations_text("common.queue", operations_locale)
                    + "\n\n"
                    + operations_text("maintenance.queue_summary", operations_locale).format(
                        shown=maintenance_filtered_count,
                        total=len(maintenance_queue.items),
                    )
                ),
                maintenance_selector,
            ],
            gap=0.8,
        )

    if selected_maintenance is None:
        _detail_panel = mo.md(
            "## "
            + operations_text("maintenance.review_heading", operations_locale)
            + "\n\n"
            + operations_text("maintenance.select_review", operations_locale)
        )
    else:
        _action_blocks = []
        if maintenance_error:
            _action_blocks.append(
                mo.Html(
                    render_operations_recovery_html(
                        "maintenance",
                        technical_detail=maintenance_error,
                        locale=operations_locale,
                    )
                )
            )
        if maintenance_success:
            _action_blocks.append(
                mo.callout(
                    maintenance_success,
                    kind="success",
                    title=operations_text("maintenance.updated", operations_locale),
                )
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
                    mo.md("### " + operations_text("maintenance.actions", operations_locale)),
                    maintenance_note_input,
                    mo.hstack(_buttons, justify="start", gap=0.6),
                ]
            )
        else:
            _action_blocks.append(
                mo.md(
                    "### "
                    + operations_text("maintenance.actions", operations_locale)
                    + "\n\n"
                    + operations_text("maintenance.closed_help", operations_locale)
                )
            )
        _evidence_blocks = [
            mo.Html(
                render_maintenance_evidence_html(
                    maintenance_evidence,
                    analysis_run_id=selected_maintenance.analysis_run_id,
                    metrics=maintenance_evidence_metrics,
                    locale=operations_locale,
                )
            )
        ]
        if maintenance_open_investigation_button is not None:
            _evidence_blocks.append(maintenance_open_investigation_button)
        _detail_panel = mo.vstack(
            [
                mo.Html(
                    render_maintenance_summary_html(
                        selected_maintenance,
                        asset_names,
                        operations_locale,
                    )
                ),
                *_evidence_blocks,
                mo.Html(
                    render_maintenance_timeline_html(
                        selected_maintenance,
                        operations_locale,
                    )
                ),
                *_action_blocks,
                mo.accordion(
                    {
                        operations_text("maintenance.review_identity", operations_locale): mo.Html(
                            render_maintenance_identity_html(
                                selected_maintenance,
                                operations_locale,
                            )
                        )
                    }
                ),
                mo.md(operations_text("maintenance.workflow_semantics", operations_locale)),
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
    operations_locale,
    operations_text,
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
                    operations_text(
                        "system.asset_name_conflict_detail",
                        operations_locale,
                    )
                    + "\n\n"
                    + _rows
                ),
                kind="warn",
                title=operations_text("system.asset_name_conflict", operations_locale),
            )
        )
    system_view = mo.vstack(
        [
            mo.Html(render_system_runtime_html(system_runtime, operations_locale)),
            mo.Html(render_system_errors_html(system_runtime, operations_locale)),
            *_name_conflicts,
            mo.accordion(
                {
                    operations_text(
                        "system.advanced_diagnostics",
                        operations_locale,
                    ): mo.Html(
                        render_system_diagnostics_html(system_diagnostics, operations_locale)
                    )
                }
            ),
            mo.md(operations_text("system.runtime_evidence_help", operations_locale)),
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
    operations_locale,
    operations_text,
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
    setup_open_monitor_button,
    setup_receipt_confirmed,
    setup_refresh_data_flow_button,
    setup_subscription_diagnostic_button,
    setup_selected_source,
    setup_source_selector,
    setup_start_collection_button,
    setup_stop_collection_button,
    setup_success,
    setup_diagnostic_error,
    setup_diagnostic_success,
    setup_workspace,
    render_operations_recovery_html,
):
    def _setup_step(title_key, help_key):
        title = operations_text(title_key, operations_locale)
        detail = operations_text(help_key, operations_locale)
        return mo.Html(
            '<div class="phm-setup-step">'
            f'<div class="phm-setup-step-title">{title}</div>'
            f'<div class="phm-setup-help">{detail}</div>'
            "</div>"
        )

    _message_blocks = []
    if setup_error:
        _message_blocks.append(
            mo.Html(
                render_operations_recovery_html(
                    "setup", technical_detail=setup_error, locale=operations_locale
                )
            )
        )
    if setup_success:
        _message_blocks.append(
            mo.callout(
                setup_success,
                kind="success",
                title=operations_text("setup.updated", operations_locale),
            )
        )

    if setup_selected_source is None:
        _selected_source_panel = mo.md(
            "### "
            + operations_text("setup.connect_first_source", operations_locale)
            + "\n\n"
            + operations_text("setup.connect_first_source_help", operations_locale)
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
                mo.Html(
                    render_setup_source_detail_html(
                        setup_selected_source,
                        operations_locale,
                    )
                ),
                mo.hstack(_source_actions, justify="start", gap=0.6),
                mo.md(operations_text("setup.source_controls_help", operations_locale)),
                mo.accordion(
                    {
                        operations_text("setup.data_age_policy", operations_locale): mo.vstack(
                            [
                                setup_freshness_age_input,
                                mo.hstack(
                                    _freshness_actions,
                                    justify="start",
                                    gap=0.6,
                                ),
                                mo.md(operations_text("setup.data_age_help", operations_locale)),
                            ],
                            gap=0.6,
                        )
                    }
                ),
                mo.accordion(
                    {
                        operations_text("setup.advanced_diagnostics", operations_locale): mo.vstack(
                            [
                                *(
                                    [
                                        mo.Html(
                                            render_operations_recovery_html(
                                                "setup.diagnostic",
                                                technical_detail=setup_diagnostic_error,
                                                locale=operations_locale,
                                            )
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
                                            title=operations_text(
                                                "setup.diagnostic_completed",
                                                operations_locale,
                                            ),
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
                                mo.md(operations_text("setup.diagnostics_help", operations_locale)),
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
                        operations_text(
                            "setup.discovered_file_summary",
                            operations_locale,
                        ).format(
                            files=file_discovery.file_count,
                            columns=len(file_discovery.common_columns),
                        )
                    ),
                    mo.ui.table(_preview_rows, selection=None),
                    file_signal_selection,
                ],
                gap=0.6,
            )
        else:
            _file_discovery_view = mo.md(
                operations_text("setup.run_discovery_help", operations_locale)
            )

        _source_wizard = mo.vstack(
            [
                mo.md("### " + operations_text("setup.add_data_source", operations_locale)),
                *(_message_blocks if setup_selected_source is None else []),
                _setup_step("setup.step.source", "setup.file.connect_help"),
                add_source_type,
                mo.hstack([add_source_id, add_source_name], widths="equal"),
                mo.hstack([add_asset_id, add_point_id], widths="equal"),
                file_mode_input,
                file_path_input,
                file_discover_button,
                _setup_step("setup.step.select_signals", "setup.file.select_help"),
                _file_discovery_view,
                _setup_step("setup.step.time_sampling", "setup.file.meaning_help"),
                mo.hstack(
                    [file_timestamp_input, file_sampling_rate_input],
                    widths="equal",
                ),
                _setup_step("setup.step.review_save", "setup.file.review_help"),
                register_setup_source_button,
            ],
            gap=0.75,
        )
    else:
        if opcua_browse_current and opcua_browse is not None:
            _browse_status = mo.md(
                operations_text("setup.browse_summary", operations_locale).format(
                    variables=len(opcua_browse.variables),
                    nodes=opcua_browse.visited_node_count,
                    truncated=(
                        operations_text("setup.result_truncated", operations_locale)
                        if opcua_browse.truncated
                        else ""
                    ),
                )
            )
        else:
            _browse_status = mo.md(operations_text("setup.browse_help", operations_locale))

        if opcua_mapping_error:
            _mapping_view = mo.Html(
                render_operations_recovery_html(
                    "setup.mapping",
                    technical_detail=opcua_mapping_error,
                    locale=operations_locale,
                )
            )
        elif opcua_candidate_mappings:
            _mapping_view = mo.ui.table(
                [
                    {
                        operations_text("common.signal", operations_locale): item.channel_id,
                        "NodeId": item.node_id,
                    }
                    for item in opcua_candidate_mappings
                ],
                selection=None,
            )
        else:
            _mapping_view = mo.md(operations_text("setup.no_mapping_selected", operations_locale))

        _semantic_rows = [
            {
                operations_text("common.signal", operations_locale): channel_id,
                operations_text("setup.observed_property", operations_locale): (
                    binding.definition.observed_property
                    or operations_text("common.unresolved", operations_locale)
                ),
                operations_text("setup.scope", operations_locale): binding.definition.scope or "—",
                operations_text("setup.statistic", operations_locale): (
                    binding.definition.statistic or "—"
                ),
                operations_text("setup.unit", operations_locale): binding.definition.unit or "—",
                operations_text("setup.version", operations_locale): binding.version,
                operations_text("common.evidence", operations_locale): (
                    binding.interpretation_evidence
                ),
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
                        else mo.md(operations_text("setup.semantic_empty", operations_locale))
                    ),
                ],
                gap=0.6,
            )
            if semantic_channel_input is not None
            else mo.md(operations_text("setup.select_mapping_first", operations_locale))
        )

        _source_wizard = mo.vstack(
            [
                mo.md("### " + operations_text("setup.add_data_source", operations_locale)),
                *(_message_blocks if setup_selected_source is None else []),
                _setup_step("setup.step.connect", "setup.opcua.connect_help"),
                add_source_type,
                mo.hstack([add_source_id, add_source_name], widths="equal"),
                mo.hstack([add_asset_id, add_point_id], widths="equal"),
                mo.hstack([opcua_endpoint_input, opcua_timeout_input], widths=[0.75, 0.25]),
                opcua_browse_button,
                _browse_status,
                _setup_step("setup.step.select_signals", "setup.opcua.select_help"),
                (
                    opcua_signal_selection
                    if opcua_signal_selection is not None
                    else mo.md(operations_text("setup.no_browse_result", operations_locale))
                ),
                _mapping_view,
                mo.accordion(
                    {
                        operations_text(
                            "setup.advanced_nodeid_mapping",
                            operations_locale,
                        ): opcua_explicit_mapping_input
                    }
                ),
                _setup_step("setup.step.define_meaning", "setup.opcua.meaning_help"),
                _semantic_editor,
                _setup_step("setup.step.review_save", "setup.opcua.review_help"),
                register_setup_source_button,
            ],
            gap=0.75,
        )

    _analysis_configuration_view = mo.vstack(
        [
            mo.md(operations_text("setup.analysis_policy_help", operations_locale)),
            mo.md(operations_text("setup.analysis_navigation_help", operations_locale)),
        ],
        gap=0.8,
    )

    if setup_selected_source is None:
        _guided_setup = mo.vstack(
            [
                mo.md(
                    "### 1 · "
                    + operations_text("setup.connect_data_title", operations_locale)
                    + "\n\n"
                    + operations_text("setup.connect_data_help", operations_locale)
                ),
                _source_wizard,
            ],
            gap=0.9,
        )
    else:
        _defined, _total = setup_selected_source.semantic_coverage
        _guided_setup = mo.vstack(
            [
                mo.md("### 1 · " + operations_text("setup.connected_source", operations_locale)),
                mo.Html(
                    render_setup_sources_html(
                        setup_workspace,
                        operations_locale,
                    )
                ),
                _selected_source_panel,
                mo.md(
                    "### 2 · "
                    + operations_text("setup.inspect_signals_title", operations_locale)
                    + "\n\n"
                    + operations_text("setup.inspect_signals_help", operations_locale)
                ),
                mo.Html(
                    render_setup_signals_html(
                        setup_selected_source,
                        operations_locale,
                    )
                ),
                mo.md(
                    "### 3 · "
                    + operations_text("setup.confirm_meaning_title", operations_locale)
                    + "\n\n"
                    + operations_text("setup.confirm_meaning_help", operations_locale).format(
                        defined=_defined,
                        total=_total,
                    )
                ),
                mo.md(
                    "### 4 · "
                    + operations_text("setup.verify_flow_title", operations_locale)
                    + "\n\n"
                    + operations_text("setup.verify_flow_help", operations_locale)
                ),
                mo.callout(
                    operations_text(
                        (
                            "setup.data_flow_confirmed"
                            if setup_receipt_confirmed
                            else "setup.data_flow_waiting"
                        ),
                        operations_locale,
                    ),
                    kind="success" if setup_receipt_confirmed else "info",
                    title=operations_text("setup.data_flow_status", operations_locale),
                ),
                setup_refresh_data_flow_button,
                mo.md(
                    "### 5 · "
                    + operations_text("setup.observe_title", operations_locale)
                    + "\n\n"
                    + operations_text(
                        (
                            "setup.observe_ready"
                            if setup_receipt_confirmed
                            else "setup.monitor_locked"
                        ),
                        operations_locale,
                    )
                ),
                *([setup_open_monitor_button] if setup_open_monitor_button is not None else []),
                mo.accordion(
                    {
                        operations_text(
                            "setup.add_another_source", operations_locale
                        ): _source_wizard,
                        operations_text(
                            "setup.analysis_configuration", operations_locale
                        ): _analysis_configuration_view,
                    }
                ),
            ],
            gap=0.9,
        )

    setup_view = mo.vstack(
        [
            mo.md(
                "## "
                + operations_text("setup.title", operations_locale)
                + "\n\n"
                + operations_text("setup.intro", operations_locale)
            ),
            *(_message_blocks if setup_selected_source is not None else []),
            _guided_setup,
        ],
        gap=1.0,
    )
    return (setup_view,)


@app.cell
def _(
    first_run_error,
    first_run_mode,
    first_run_real_button,
    first_run_sample,
    first_run_sample_button,
    first_run_stop_sample_button,
    mo,
    operations_locale,
    operations_text,
    render_operations_recovery_html,
):
    if first_run_mode == "sample" and first_run_sample is not None:
        first_run_view = mo.vstack(
            [
                mo.md(
                    f"## {operations_text('first_run.sample.ready', operations_locale)}\n\n"
                    f"{operations_text('first_run.sample.isolation', operations_locale)}"
                ),
                mo.Html(
                    f'<a href="{first_run_sample.url}" target="_blank" rel="noopener noreferrer">'
                    f"{operations_text('first_run.sample.open', operations_locale)}</a>"
                ),
                mo.md(
                    operations_text("first_run.sample.workspace", operations_locale).format(
                        workspace=first_run_sample.workspace
                    )
                ),
                mo.hstack(
                    [first_run_stop_sample_button, first_run_real_button],
                    justify="start",
                    gap=0.6,
                ),
            ],
            gap=1.0,
        )
    else:
        _blocks = [
            mo.md(
                f"# {operations_text('first_run.title', operations_locale)}\n\n"
                f"{operations_text('first_run.intro', operations_locale)}"
            ),
        ]
        if first_run_error:
            _blocks.append(
                mo.Html(
                    render_operations_recovery_html(
                        "first_run.sample",
                        technical_detail=first_run_error,
                        locale=operations_locale,
                    )
                )
            )
        _blocks.extend(
            [
                mo.hstack(
                    [
                        mo.vstack(
                            [
                                mo.md(
                                    "### "
                                    + operations_text(
                                        "first_run.sample.title",
                                        operations_locale,
                                    )
                                    + "\n\n"
                                    + operations_text(
                                        "first_run.sample.detail",
                                        operations_locale,
                                    )
                                ),
                                first_run_sample_button,
                            ],
                            gap=0.6,
                        ),
                        mo.vstack(
                            [
                                mo.md(
                                    "### "
                                    + operations_text(
                                        "first_run.real.title",
                                        operations_locale,
                                    )
                                    + "\n\n"
                                    + operations_text(
                                        "first_run.real.detail",
                                        operations_locale,
                                    )
                                ),
                                first_run_real_button,
                            ],
                            gap=0.6,
                        ),
                    ],
                    widths="equal",
                    align="start",
                    gap=1.0,
                ),
                mo.md(operations_text("first_run.resume", operations_locale)),
            ]
        )
        first_run_view = mo.vstack(_blocks, gap=1.0)
    return (first_run_view,)


@app.cell
def _(asset_selector, monitor, monitor_context_attention):
    contextual_attention = (
        ()
        if asset_selector is None
        else monitor_context_attention(monitor.attention, asset_id=asset_selector.value)
    )
    return (contextual_attention,)


@app.cell
def _(
    OPERATIONS_PAGE_OPTIONS,
    asset_names,
    asset_selector,
    asset_workspace,
    asset_workspace_error,
    contextual_attention,
    first_run_mode,
    get_monitor_comparisons,
    get_monitor_revision,
    get_investigation_selection,
    history_assets,
    investigation_capability_label,
    investigation_queue,
    investigation_review_label,
    mo,
    monitor,
    monitor_chart_data,
    monitor_chart_error,
    monitor_latest_rows,
    monitor_latest_error,
    monitor_comparison_channels,
    monitor_range_id,
    monitor_attention_category,
    monitor_window_evidence_items,
    navigation_page,
    operations_locale,
    operations_messages,
    operations_page_label,
    operations_text,
    registered_sources,
    resolve_investigation_route,
    resolve_operations_attention_route,
    set_asset_section,
    set_asset_selection,
    set_investigation_asset_filter,
    set_investigation_capability_filter,
    set_investigation_review_filter,
    set_investigation_selection,
    set_monitor_comparisons,
    set_monitor_range,
    set_monitor_revision,
    set_navigation_page,
    set_signal_channel_choice,
    setup_receipt_confirmed,
    signal_channel_selector,
):
    from industrial_phm.apps.monitor_widget import MonitorWidget
    from industrial_phm.presentation.monitor_workspace import (
        chart_payload,
        signal_payload,
        utc_millis,
    )
    from industrial_phm.presentation.operations_shell import data_status_label

    _assets = sorted({item.asset_id for item in (*monitor.assets, *history_assets)})
    _focus = None if signal_channel_selector is None else signal_channel_selector.value
    _selected_asset = None if asset_selector is None else asset_selector.value
    _comparisons = list(monitor_comparison_channels)
    _catalog_rows = signal_payload(monitor_latest_rows, registered_sources, _selected_asset)
    _onboarding_locked = first_run_mode != "configured" and not setup_receipt_confirmed
    _allowed_pages = [
        page.value
        for page in OPERATIONS_PAGE_OPTIONS
        if not _onboarding_locked or page.value == "setup"
    ]
    _allowed_channels = {row["channel"] for row in _catalog_rows} | (
        set() if asset_workspace is None else set(asset_workspace.history_channels)
    )
    _payload = {
        "page": str(navigation_page),
        "locale": operations_locale.value,
        "messages": operations_messages(operations_locale),
        "active_investigation": get_investigation_selection(),
        "pages": _allowed_pages,
        "page_labels": {
            page.value: operations_page_label(page, operations_locale)
            for page in OPERATIONS_PAGE_OPTIONS
        },
        "asset_id": _selected_asset,
        "asset_name": None if _selected_asset is None else asset_names.label(_selected_asset),
        "assets": [{"id": asset, "name": asset_names.label(asset)} for asset in _assets],
        "status_id": (
            "no-source-context" if asset_workspace is None else asset_workspace.status.value
        ),
        "status": (
            operations_text("monitor.no_source_context", operations_locale)
            if asset_workspace is None
            else data_status_label(asset_workspace.status, operations_locale)
        ),
        "source_at": (
            None if asset_workspace is None else utc_millis(asset_workspace.last_data_at)
        ),
        "assessed_at": utc_millis(monitor.assessed_at),
        "signals": _catalog_rows,
        "stored_signal_count": len(monitor_latest_rows),
        "focus": _focus,
        "comparisons": _comparisons,
        "range": monitor_range_id,
        "chart": chart_payload(monitor_chart_data, [_focus, *_comparisons]),
        "error": asset_workspace_error or monitor_latest_error or monitor_chart_error,
        "evidence": [
            {
                "id": item.investigation_id,
                "label": investigation_capability_label(
                    item.capability_id,
                    operations_locale,
                ),
                "start": utc_millis(item.observed_start_at),
                "end": utc_millis(item.observed_end_at),
                "review": investigation_review_label(
                    item.review_state,
                    operations_locale,
                ),
            }
            for item in monitor_window_evidence_items
        ],
        "attention": [
            {
                "id": item.attention_id,
                "title": item.title,
                "detail": item.detail,
                "category": monitor_attention_category(item, operations_locale),
            }
            for item in contextual_attention
        ],
    }

    def _navigate_route(route):
        if route.page == "assets":
            set_asset_selection(route.asset_id)
            set_asset_section(route.asset_section)
        elif route.page == "investigations":
            set_investigation_review_filter("all")
            set_investigation_asset_filter("all")
            set_investigation_capability_filter("all")
            set_investigation_selection((route.investigation_group_id, route.investigation_id))
        set_navigation_page(route.page)

    def _handle_monitor_event(event):
        _kind = event.get("kind")
        if (
            _kind == "navigate"
            and isinstance(event.get("page"), str)
            and event["page"] in set(_allowed_pages)
        ):
            set_navigation_page(event["page"])
        elif _kind == "asset" and event.get("id") in _assets:
            set_asset_selection(event["id"])
        elif (
            _kind == "focus"
            and isinstance(event.get("channel"), str)
            and event["channel"] in _allowed_channels
        ):
            set_signal_channel_choice(event["channel"])
        elif _kind == "compare" and isinstance(event.get("channels"), list):
            _valid = list(
                dict.fromkeys(
                    channel
                    for channel in event["channels"]
                    if isinstance(channel, str)
                    and channel in _allowed_channels
                    and channel != _focus
                )
            )[:5]
            set_monitor_comparisons({**get_monitor_comparisons(), _selected_asset: _valid})
        elif (
            _kind == "range"
            and isinstance(event.get("range"), str)
            and event["range"] in {"15m", "1h", "24h", "7d"}
        ):
            set_monitor_range(event["range"])
        elif _kind == "detail" and _selected_asset is not None:
            set_asset_section("signals")
            set_navigation_page("assets")
        elif _kind == "refresh":
            set_monitor_revision(get_monitor_revision() + 1)
        elif (
            _kind == "evidence"
            and isinstance(event.get("id"), str)
            and event["id"] in {item.investigation_id for item in monitor_window_evidence_items}
        ):
            _navigate_route(
                resolve_investigation_route(event["id"], investigation_queue=investigation_queue)
            )
        elif _kind == "attention":
            _item = next(
                (item for item in contextual_attention if item.attention_id == event.get("id")),
                None,
            )
            if _item is None:
                return False
            if _item is not None:
                _navigate_route(
                    resolve_operations_attention_route(
                        _item, investigation_queue=investigation_queue
                    )
                )
        else:
            return False
        return True

    monitor_workspace_ui = mo.ui.anywidget(MonitorWidget(_payload, _handle_monitor_event))
    return (monitor_workspace_ui,)


@app.cell
def _(
    asset_analysis_view,
    asset_names,
    asset_section,
    asset_selector,
    asset_workspace,
    asset_workspace_css,
    asset_workspace_error,
    investigation_view,
    first_run_mode,
    first_run_view,
    investigation_workspace_css,
    locale_selector,
    maintenance_view,
    mo,
    monitor_workspace_ui,
    navigation_page,
    operations_locale,
    operations_text,
    operations_theme_css,
    render_asset_analysis_html,
    render_asset_events_html,
    render_asset_header_html,
    render_asset_maintenance_html,
    render_asset_overview_html,
    setup_view,
    setup_workspace,
    setup_workspace_css,
    signal_view,
    system_view,
    system_workspace_css,
    render_operations_recovery_html,
    operations_error_css,
):
    theme = mo.Html(
        operations_theme_css(operations_locale)
        + asset_workspace_css()
        + investigation_workspace_css()
        + system_workspace_css()
        + setup_workspace_css()
        + operations_error_css()
    )

    if asset_selector is None:
        asset_view = mo.md(
            "## "
            + operations_text("asset.title", operations_locale)
            + "\n\n"
            + operations_text("asset.no_evidence", operations_locale)
        )
    elif asset_workspace_error:
        asset_view = mo.vstack(
            [
                asset_selector,
                mo.Html(
                    render_operations_recovery_html(
                        "asset.workspace",
                        technical_detail=asset_workspace_error,
                        locale=operations_locale,
                    )
                ),
            ],
            gap=1.0,
        )
    elif asset_workspace is None:
        asset_view = mo.vstack(
            [
                asset_selector,
                mo.md(operations_text("asset.load_hint", operations_locale)),
            ],
            gap=1.0,
        )
    else:
        _asset_sections = {
            "overview": mo.Html(render_asset_overview_html(asset_workspace, operations_locale)),
            "signals": signal_view,
            "analysis": asset_analysis_view,
            "events": mo.Html(render_asset_events_html(asset_workspace, operations_locale)),
            "maintenance": mo.Html(
                render_asset_maintenance_html(asset_workspace, operations_locale)
            ),
        }
        asset_view = mo.vstack(
            [
                mo.hstack(
                    [asset_selector, asset_section],
                    widths=[0.46, 0.54],
                    align="start",
                ),
                mo.Html(render_asset_header_html(asset_workspace, asset_names, operations_locale)),
                _asset_sections[asset_section.value],
            ],
            gap=1.1,
        )

    _setup_page = (
        first_run_view if not setup_workspace.sources and first_run_mode != "real" else setup_view
    )
    pages = {
        "monitor": monitor_workspace_ui,
        "assets": asset_view,
        "investigations": investigation_view,
        "maintenance": maintenance_view,
        "system": system_view,
        "setup": _setup_page,
    }

    shell = (
        monitor_workspace_ui
        if navigation_page == "monitor"
        else mo.vstack([monitor_workspace_ui, pages[navigation_page]], gap=0.8)
    )
    mo.vstack(
        [
            theme,
            mo.hstack([locale_selector], justify="end"),
            shell,
        ],
        gap=0.35,
    )
    return


if __name__ == "__main__":
    app.run()
