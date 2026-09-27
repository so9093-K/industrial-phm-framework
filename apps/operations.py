import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import asyncio
    import os
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    from pathlib import Path

    import marimo as mo

    from industrial_phm.adapters import CsvSensorLayout, CsvSensorSourceError
    from industrial_phm.application import (
        AssetObservationSummary,
        AssetObservationTimeline,
        FileSourceConfig,
        FileSourceMode,
        FindingReviewAction,
        FindingReviewStatus,
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        OpcUaSourceConfig,
        RegisteredSource,
        SourceFreshnessPolicy,
        SourceLifecycleState,
        SourceRuntimeCycleState,
        SourceType,
        assess_source_freshness,
        assess_source_health,
        create_finding_review_event,
        create_human_review_finding,
        discover_file_source,
        finding_review_status,
        load_field_csv_observation_summary,
        load_field_csv_observation_timeline_directory,
        load_registered_file_source_observation,
        project_registered_opcua_observation_summary,
        receive_registered_file_source_observation,
        register_file_source,
        run_registered_file_feature_analysis,
        run_registered_file_source_cycle,
        run_registered_opcua_source_cycle,
        run_registered_opcua_subscription_cycle,
        transition_source_lifecycle,
        validate_distinct_source_state_paths,
        validate_registered_file_source,
    )
    from industrial_phm.connectors import (
        OpcUaBrowseConfig,
        OpcUaNodeMapping,
        browse_opcua_variables,
    )
    from industrial_phm.contracts import DataQualityState

    return (
        AssetObservationSummary,
        AssetObservationTimeline,
        CsvSensorLayout,
        CsvSensorSourceError,
        DataQualityState,
        FileSourceConfig,
        FileSourceMode,
        FindingReviewAction,
        FindingReviewStatus,
        JsonFieldFeatureAnalysisRepository,
        JsonFindingReviewRepository,
        JsonOperationalFindingRepository,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        OpcUaBrowseConfig,
        OpcUaNodeMapping,
        OpcUaSourceConfig,
        Path,
        RegisteredSource,
        SourceFreshnessPolicy,
        SourceLifecycleState,
        SourceRuntimeCycleState,
        SourceType,
        assess_source_freshness,
        assess_source_health,
        asyncio,
        browse_opcua_variables,
        create_finding_review_event,
        create_human_review_finding,
        datetime,
        discover_file_source,
        finding_review_status,
        load_field_csv_observation_summary,
        load_field_csv_observation_timeline_directory,
        load_registered_file_source_observation,
        project_registered_opcua_observation_summary,
        receive_registered_file_source_observation,
        mo,
        register_file_source,
        run_registered_file_feature_analysis,
        run_registered_file_source_cycle,
        run_registered_opcua_source_cycle,
        run_registered_opcua_subscription_cycle,
        transition_source_lifecycle,
        validate_distinct_source_state_paths,
        validate_registered_file_source,
        ThreadPoolExecutor,
        os,
    )


@app.cell
def _(JsonFieldFeatureAnalysisRepository, Path, os):
    field_analysis_state_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_STATE",
            "artifacts/operations/field-analysis.json",
        )
    )
    try:
        initial_field_analysis_results = JsonFieldFeatureAnalysisRepository(
            field_analysis_state_path
        ).list_results()
        field_analysis_state_error = ""
    except (OSError, ValueError) as error:
        initial_field_analysis_results = ()
        field_analysis_state_error = str(error)
    return (
        field_analysis_state_error,
        field_analysis_state_path,
        initial_field_analysis_results,
    )


@app.cell
def _(JsonOperationalFindingRepository, Path, os):
    finding_state_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_FINDING_STATE",
            "artifacts/operations/findings.json",
        )
    )
    try:
        initial_operational_findings = JsonOperationalFindingRepository(
            finding_state_path
        ).list_findings()
        finding_state_error = ""
    except (OSError, ValueError) as error:
        initial_operational_findings = ()
        finding_state_error = str(error)
    return finding_state_error, finding_state_path, initial_operational_findings


@app.cell
def _(JsonFindingReviewRepository, Path, os):
    finding_review_state_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_OPERATIONS_MAINTENANCE_REVIEW_STATE",
            "artifacts/operations/finding-review.json",
        )
    )
    try:
        initial_finding_review_events = JsonFindingReviewRepository(
            finding_review_state_path
        ).list_events()
        finding_review_state_error = ""
    except (OSError, ValueError) as error:
        initial_finding_review_events = ()
        finding_review_state_error = str(error)
    return (
        finding_review_state_error,
        finding_review_state_path,
        initial_finding_review_events,
    )


@app.cell
def _(
    CsvSensorLayout,
    CsvSensorSourceError,
    OpcUaBrowseConfig,
    OpcUaNodeMapping,
    Path,
    ThreadPoolExecutor,
    asyncio,
    browse_opcua_variables,
    load_field_csv_observation_summary,
    load_field_csv_observation_timeline_directory,
):
    def parse_channels(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def parse_sampling_rate(value: str) -> float | None:
        return None if not value.strip() else float(value)

    def parse_opcua_node_mappings(value: str):
        mappings = []
        for line_number, raw_line in enumerate(value.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if "," not in line:
                raise ValueError(
                    f"OPC UA node mapping line {line_number} must use channel_id,node_id"
                )
            channel_id, node_id = line.split(",", 1)
            mappings.append(
                OpcUaNodeMapping(
                    channel_id=channel_id.strip(),
                    node_id=node_id.strip(),
                )
            )
        return tuple(mappings)

    def run_opcua_browse(*, endpoint_url: str, timeout_seconds: float):
        config = OpcUaBrowseConfig(
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
        )

        def _run():
            return asyncio.run(browse_opcua_variables(config))

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(_run).result()

    def load_observation(
        *,
        source_path: str,
        history_directory: str,
        asset_id: str,
        source_id: str,
        measurement_point_id: str,
        channels: str,
        timestamp_column: str,
        sampling_rate_hz: str,
    ):
        path_value = source_path.strip()
        history_value = history_directory.strip()
        if not path_value and not history_value:
            return None, None, ""

        layout = CsvSensorLayout(
            asset_id=asset_id.strip(),
            timestamp_column=timestamp_column.strip() or None,
            channel_columns=parse_channels(channels),
            sampling_rate_hz=parse_sampling_rate(sampling_rate_hz),
        )
        try:
            if history_value:
                timeline = load_field_csv_observation_timeline_directory(
                    Path(history_value),
                    layout,
                    source_id=source_id.strip(),
                    measurement_point_id=measurement_point_id.strip() or None,
                )
                return timeline.latest, timeline, ""

            summary = load_field_csv_observation_summary(
                Path(path_value),
                layout,
                source_id=source_id.strip(),
                measurement_point_id=measurement_point_id.strip() or None,
            )
        except (CsvSensorSourceError, OSError, ValueError) as error:
            return None, None, str(error)

        return summary, None, ""

    return (
        load_observation,
        parse_channels,
        parse_opcua_node_mappings,
        parse_sampling_rate,
        run_opcua_browse,
    )


@app.cell
def _(
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    Path,
    load_observation,
    os,
    validate_distinct_source_state_paths,
):
    source_registry_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY",
        "artifacts/operations/source-registry.json",
    )
    source_runtime_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_SOURCE_RUNTIME",
        "artifacts/operations/source-runtime.json",
    )
    try:
        _source_repository = JsonSourceRepository(Path(source_registry_default))
        initial_registered_sources = _source_repository.list_sources()
        initial_source_lifecycle_records = tuple(
            _source_repository.get_lifecycle(source.source_id)
            for source in initial_registered_sources
        )
        initial_source_freshness_policies = tuple(
            _policy
            for source in initial_registered_sources
            if (_policy := _source_repository.get_freshness_policy(source.source_id)) is not None
        )
        initial_source_registry_error = ""
    except (OSError, ValueError) as error:
        initial_registered_sources = ()
        initial_source_lifecycle_records = ()
        initial_source_freshness_policies = ()
        initial_source_registry_error = str(error)

    try:
        _registry_path = Path(source_registry_default)
        _runtime_path = Path(source_runtime_default)
        validate_distinct_source_state_paths(_registry_path, _runtime_path)
        _runtime_repository = JsonSourceRuntimeRepository(_runtime_path)
        _registered_source_ids = {source.source_id for source in initial_registered_sources}
        initial_source_runtime_receipts = tuple(
            receipt
            for receipt in _runtime_repository.list_latest_receipts()
            if receipt.source_id in _registered_source_ids
        )
        initial_source_runtime_connection_attempts = tuple(
            attempt
            for attempt in _runtime_repository.list_latest_connection_attempts()
            if attempt.source_id in _registered_source_ids
        )
        initial_source_runtime_error = ""
    except (OSError, ValueError) as error:
        initial_source_runtime_receipts = ()
        initial_source_runtime_connection_attempts = ()
        initial_source_runtime_error = str(error)

    source_default = os.environ.get("INDUSTRIAL_PHM_OPERATIONS_SOURCE", "")
    history_directory_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_HISTORY_DIRECTORY",
        "",
    )
    asset_default = os.environ.get("INDUSTRIAL_PHM_OPERATIONS_ASSET_ID", "asset-01")
    source_id_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_SOURCE_ID",
        "prepared-field-csv",
    )
    measurement_point_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_MEASUREMENT_POINT_ID",
        "",
    )
    channels_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_CHANNELS",
        "vibration_x",
    )
    timestamp_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_TIMESTAMP_COLUMN",
        "timestamp",
    )
    sampling_rate_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_SAMPLING_RATE_HZ",
        "",
    )

    initial_summary, initial_timeline, initial_error = load_observation(
        source_path=source_default,
        history_directory=history_directory_default,
        asset_id=asset_default,
        source_id=source_id_default,
        measurement_point_id=measurement_point_default,
        channels=channels_default,
        timestamp_column=timestamp_default,
        sampling_rate_hz=sampling_rate_default,
    )
    return (
        asset_default,
        channels_default,
        history_directory_default,
        initial_error,
        initial_summary,
        initial_timeline,
        measurement_point_default,
        sampling_rate_default,
        initial_registered_sources,
        initial_source_freshness_policies,
        initial_source_lifecycle_records,
        initial_source_registry_error,
        initial_source_runtime_connection_attempts,
        initial_source_runtime_error,
        initial_source_runtime_receipts,
        source_default,
        source_id_default,
        source_registry_default,
        source_runtime_default,
        timestamp_default,
    )


@app.cell
def _(
    initial_registered_sources,
    initial_source_freshness_policies,
    initial_source_lifecycle_records,
    initial_source_registry_error,
    initial_source_runtime_connection_attempts,
    initial_source_runtime_error,
    initial_source_runtime_receipts,
    mo,
):
    get_registered_sources, set_registered_sources = mo.state(initial_registered_sources)
    get_source_freshness_policies, set_source_freshness_policies = mo.state(
        initial_source_freshness_policies
    )
    get_source_lifecycle_records, set_source_lifecycle_records = mo.state(
        initial_source_lifecycle_records
    )
    get_source_registry_error, set_source_registry_error = mo.state(initial_source_registry_error)
    get_source_runtime_error, set_source_runtime_error = mo.state(initial_source_runtime_error)
    get_source_runtime_connection_attempts, set_source_runtime_connection_attempts = mo.state(
        initial_source_runtime_connection_attempts
    )
    get_source_runtime_receipts, set_source_runtime_receipts = mo.state(
        initial_source_runtime_receipts
    )
    return (
        get_registered_sources,
        get_source_freshness_policies,
        get_source_lifecycle_records,
        get_source_registry_error,
        get_source_runtime_connection_attempts,
        get_source_runtime_error,
        get_source_runtime_receipts,
        set_registered_sources,
        set_source_freshness_policies,
        set_source_lifecycle_records,
        set_source_registry_error,
        set_source_runtime_connection_attempts,
        set_source_runtime_error,
        set_source_runtime_receipts,
    )


@app.cell
def _(
    get_registered_sources,
    get_source_freshness_policies,
    get_source_lifecycle_records,
    get_source_registry_error,
    get_source_runtime_connection_attempts,
    get_source_runtime_error,
    get_source_runtime_receipts,
):
    registered_sources = get_registered_sources()
    source_freshness_policies = get_source_freshness_policies()
    source_lifecycle_records = get_source_lifecycle_records()
    source_registry_error = get_source_registry_error()
    source_runtime_connection_attempts = get_source_runtime_connection_attempts()
    source_runtime_error = get_source_runtime_error()
    source_runtime_receipts = get_source_runtime_receipts()
    return (
        registered_sources,
        source_freshness_policies,
        source_lifecycle_records,
        source_registry_error,
        source_runtime_connection_attempts,
        source_runtime_error,
        source_runtime_receipts,
    )


@app.cell
def _(mo):
    get_demo_prepare_error, set_demo_prepare_error = mo.state("")
    get_demo_prepare_success, set_demo_prepare_success = mo.state("")
    return (
        get_demo_prepare_error,
        get_demo_prepare_success,
        set_demo_prepare_error,
        set_demo_prepare_success,
    )


@app.cell
def _(get_demo_prepare_error, get_demo_prepare_success):
    demo_prepare_error = get_demo_prepare_error()
    demo_prepare_success = get_demo_prepare_success()
    return demo_prepare_error, demo_prepare_success


@app.cell
def _(
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    Path,
    RegisteredSource,
    datetime,
    load_registered_file_source_observation,
    prepare_demo_source_button,
    register_file_source,
    set_demo_prepare_error,
    set_demo_prepare_success,
    set_load_error,
    set_observation,
    set_registered_sources,
    set_source_freshness_policies,
    set_source_lifecycle_records,
    set_source_registry_error,
    set_timeline,
    source_registry_default,
    validate_registered_file_source,
):
    if prepare_demo_source_button.value:
        try:
            _demo_path = (
                Path(__file__).resolve().parents[1]
                / "examples"
                / "operations"
                / "demo-bearing-snapshot.csv"
            )
            _config = FileSourceConfig(
                source_path=str(_demo_path),
                asset_id="demo-bearing-01",
                measurement_point_id="drive-end",
                channel_columns=("vibration_x",),
                mode=FileSourceMode.SNAPSHOT,
                timestamp_column="timestamp",
                sampling_rate_hz=1.0,
                sampling_rate_tolerance_ratio=0.01,
                minimum_sample_count=16,
            )
            _repository = JsonSourceRepository(Path(source_registry_default))
            _existing = next(
                (
                    source
                    for source in _repository.list_sources()
                    if source.source_id == "demo-bearing-snapshot"
                ),
                None,
            )
            if _existing is None:
                _source = RegisteredSource(
                    source_id="demo-bearing-snapshot",
                    name="Bundled demo bearing snapshot",
                    config=_config,
                    registered_at=datetime.now().astimezone(),
                )
                _validation = register_file_source(_source, _repository)
                _action = "registered"
            else:
                if _existing.config != _config:
                    raise ValueError(
                        "demo-bearing-snapshot is already registered with a different config"
                    )
                _source = _existing
                _validation = validate_registered_file_source(_source)
                _action = "revalidated"

            _loaded = load_registered_file_source_observation(_source)
            _sources = _repository.list_sources()
            _lifecycle = tuple(_repository.get_lifecycle(source.source_id) for source in _sources)
            _freshness = tuple(
                policy
                for source in _sources
                if (policy := _repository.get_freshness_policy(source.source_id)) is not None
            )
        except (OSError, ValueError) as error:
            set_demo_prepare_success("")
            set_demo_prepare_error(str(error))
        else:
            set_registered_sources(_sources)
            set_source_lifecycle_records(_lifecycle)
            set_source_freshness_policies(_freshness)
            set_source_registry_error("")
            set_observation(_loaded.latest)
            set_timeline(_loaded.timeline)
            set_load_error("")
            set_demo_prepare_error("")
            set_demo_prepare_success(
                f"Bundled demo source {_action}: {_source.source_id} · "
                f"{_validation.total_sample_count} samples"
            )
    return


@app.cell
def _(
    asset_default,
    channels_default,
    history_directory_default,
    measurement_point_default,
    mo,
    sampling_rate_default,
    source_default,
    source_id_default,
    timestamp_default,
):
    page_selector = mo.ui.radio(
        options=[
            "Overview",
            "Sources",
            "Investigation",
            "Data Quality",
            "Maintenance Review",
            "Operational State",
        ],
        value="Overview",
        inline=True,
        label="Operations",
    )
    source_input = mo.ui.text(
        value=source_default,
        label="Prepared field CSV path",
        full_width=True,
    )
    history_directory_input = mo.ui.text(
        value=history_directory_default,
        label="Prepared history directory (optional; takes precedence)",
        full_width=True,
    )
    asset_input = mo.ui.text(value=asset_default, label="Asset ID", full_width=True)
    source_id_input = mo.ui.text(
        value=source_id_default,
        label="Source ID",
        full_width=True,
    )
    measurement_point_input = mo.ui.text(
        value=measurement_point_default,
        label="Measurement point",
        full_width=True,
    )
    channels_input = mo.ui.text(
        value=channels_default,
        label="Channels (comma-separated)",
        full_width=True,
    )
    timestamp_input = mo.ui.text(
        value=timestamp_default,
        label="Timestamp column",
        full_width=True,
    )
    sampling_rate_input = mo.ui.text(
        value=sampling_rate_default,
        label="Declared sampling rate Hz (optional)",
        full_width=True,
    )
    load_button = mo.ui.run_button(label="Load observation", kind="success")
    prepare_demo_source_button = mo.ui.run_button(
        label="Prepare bundled demo source",
        kind="success",
    )
    return (
        asset_input,
        prepare_demo_source_button,
        channels_input,
        history_directory_input,
        load_button,
        measurement_point_input,
        page_selector,
        sampling_rate_input,
        source_id_input,
        source_input,
        timestamp_input,
    )


@app.cell
def _(FileSourceMode, SourceType, mo, os):
    _registration_type_default = os.environ.get(
        "INDUSTRIAL_PHM_OPERATIONS_REGISTRATION_TYPE",
        SourceType.FILE.value,
    )
    if _registration_type_default not in {
        SourceType.FILE.value,
        SourceType.OPCUA.value,
    }:
        _registration_type_default = SourceType.FILE.value

    registration_type_input = mo.ui.radio(
        options=[SourceType.FILE.value, SourceType.OPCUA.value],
        value=_registration_type_default,
        inline=True,
        label="Source type",
    )
    registration_mode_input = mo.ui.radio(
        options=[
            FileSourceMode.SNAPSHOT.value,
            FileSourceMode.HISTORY_DIRECTORY.value,
        ],
        value=FileSourceMode.SNAPSHOT.value,
        inline=True,
        label="File source mode",
    )
    registration_path_input = mo.ui.text(
        value="",
        label="CSV file or history directory path",
        full_width=True,
    )
    registration_delimiter_input = mo.ui.text(value=",", label="Delimiter")
    discover_source_button = mo.ui.run_button(label="Discover source")

    registration_source_id_input = mo.ui.text(value="", label="Source ID", full_width=True)
    registration_name_input = mo.ui.text(value="", label="Source name", full_width=True)
    registration_asset_id_input = mo.ui.text(value="asset-01", label="Asset ID", full_width=True)
    registration_measurement_point_input = mo.ui.text(
        value="",
        label="Measurement point (optional)",
        full_width=True,
    )
    registration_channels_input = mo.ui.text(
        value="",
        label="Channels (comma-separated)",
        full_width=True,
    )
    registration_timestamp_input = mo.ui.text(
        value="timestamp",
        label="Timestamp column (optional for snapshot)",
        full_width=True,
    )
    registration_sampling_rate_input = mo.ui.text(
        value="",
        label="Declared sampling rate Hz (optional)",
        full_width=True,
    )
    registration_tolerance_input = mo.ui.text(
        value="",
        label="Sampling-rate tolerance ratio (optional)",
        full_width=True,
    )
    registration_minimum_samples_input = mo.ui.text(
        value="1",
        label="Minimum samples per CSV",
        full_width=True,
    )
    register_source_button = mo.ui.run_button(label="Validate & Register", kind="success")

    registration_opcua_endpoint_input = mo.ui.text(
        value="",
        label="OPC UA endpoint",
        placeholder="opc.tcp://host:4840",
        full_width=True,
    )
    registration_opcua_node_mappings_input = mo.ui.text_area(
        value="",
        label="Node mappings (one per line: channel_id,node_id)",
        placeholder=(
            "vibration_x,ns=2;s=Machine/VibrationX\ntemperature,ns=2;s=Machine/Temperature"
        ),
    )
    registration_opcua_timeout_input = mo.ui.text(
        value="4",
        label="Request timeout seconds",
    )
    browse_opcua_source_button = mo.ui.run_button(label="Browse variables")
    register_opcua_source_button = mo.ui.run_button(
        label="Register OPC UA source",
        kind="success",
    )
    return (
        browse_opcua_source_button,
        discover_source_button,
        register_opcua_source_button,
        register_source_button,
        registration_asset_id_input,
        registration_channels_input,
        registration_delimiter_input,
        registration_measurement_point_input,
        registration_minimum_samples_input,
        registration_mode_input,
        registration_name_input,
        registration_opcua_endpoint_input,
        registration_opcua_node_mappings_input,
        registration_opcua_timeout_input,
        registration_path_input,
        registration_sampling_rate_input,
        registration_source_id_input,
        registration_timestamp_input,
        registration_tolerance_input,
        registration_type_input,
    )


@app.cell
def _(mo):
    get_source_discovery, set_source_discovery = mo.state(None)
    get_discovery_signature, set_discovery_signature = mo.state(None)
    get_opcua_browse_result, set_opcua_browse_result = mo.state(None)
    get_opcua_browse_signature, set_opcua_browse_signature = mo.state(None)
    get_opcua_browse_error, set_opcua_browse_error = mo.state("")
    get_registration_validation, set_registration_validation = mo.state(None)
    get_registration_error, set_registration_error = mo.state("")
    get_registration_success, set_registration_success = mo.state("")
    return (
        get_discovery_signature,
        get_opcua_browse_error,
        get_opcua_browse_result,
        get_opcua_browse_signature,
        get_registration_error,
        get_registration_success,
        get_registration_validation,
        get_source_discovery,
        set_discovery_signature,
        set_opcua_browse_error,
        set_opcua_browse_result,
        set_opcua_browse_signature,
        set_registration_error,
        set_registration_success,
        set_registration_validation,
        set_source_discovery,
    )


@app.cell
def _(
    FileSourceMode,
    Path,
    SourceType,
    discover_file_source,
    discover_source_button,
    registration_delimiter_input,
    registration_mode_input,
    registration_path_input,
    registration_type_input,
    set_discovery_signature,
    set_registration_error,
    set_registration_success,
    set_registration_validation,
    set_source_discovery,
):
    if discover_source_button.value and registration_type_input.value == SourceType.FILE.value:
        _path_value = registration_path_input.value.strip()
        _delimiter = registration_delimiter_input.value
        _mode_value = registration_mode_input.value
        try:
            if not _path_value:
                raise ValueError("source path must not be empty")
            _discovery = discover_file_source(
                Path(_path_value),
                FileSourceMode(_mode_value),
                delimiter=_delimiter,
            )
        except (OSError, ValueError) as error:
            set_source_discovery(None)
            set_discovery_signature(None)
            set_registration_error(str(error))
        else:
            set_source_discovery(_discovery)
            set_discovery_signature((_mode_value, _path_value, _delimiter))
            set_registration_error("")
        set_registration_validation(None)
        set_registration_success("")
    return


@app.cell
def _(
    get_discovery_signature,
    get_opcua_browse_error,
    get_opcua_browse_result,
    get_opcua_browse_signature,
    get_registration_error,
    get_registration_success,
    get_registration_validation,
    get_source_discovery,
):
    discovery_signature = get_discovery_signature()
    opcua_browse_error = get_opcua_browse_error()
    opcua_browse_result = get_opcua_browse_result()
    opcua_browse_signature = get_opcua_browse_signature()
    registration_error = get_registration_error()
    registration_success = get_registration_success()
    registration_validation = get_registration_validation()
    source_discovery = get_source_discovery()
    return (
        discovery_signature,
        opcua_browse_error,
        opcua_browse_result,
        opcua_browse_signature,
        registration_error,
        registration_success,
        registration_validation,
        source_discovery,
    )


@app.cell
def _(
    SourceType,
    browse_opcua_source_button,
    registration_opcua_endpoint_input,
    registration_opcua_timeout_input,
    registration_type_input,
    run_opcua_browse,
    set_opcua_browse_error,
    set_opcua_browse_result,
    set_opcua_browse_signature,
    set_registration_error,
    set_registration_success,
    set_registration_validation,
):
    if browse_opcua_source_button.value and registration_type_input.value == SourceType.OPCUA.value:
        _endpoint = registration_opcua_endpoint_input.value.strip()
        _timeout_text = registration_opcua_timeout_input.value.strip()
        try:
            _result = run_opcua_browse(
                endpoint_url=_endpoint,
                timeout_seconds=float(_timeout_text),
            )
        except Exception as error:
            set_opcua_browse_result(None)
            set_opcua_browse_signature(None)
            set_opcua_browse_error(str(error))
        else:
            set_opcua_browse_result(_result)
            set_opcua_browse_signature((_endpoint, _timeout_text))
            set_opcua_browse_error("")
        set_registration_validation(None)
        set_registration_error("")
        set_registration_success("")
    return


@app.cell
def _(
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    Path,
    RegisteredSource,
    SourceType,
    datetime,
    discovery_signature,
    parse_channels,
    register_file_source,
    register_source_button,
    registration_asset_id_input,
    registration_channels_input,
    registration_delimiter_input,
    registration_measurement_point_input,
    registration_minimum_samples_input,
    registration_mode_input,
    registration_name_input,
    registration_path_input,
    registration_sampling_rate_input,
    registration_source_id_input,
    registration_timestamp_input,
    registration_tolerance_input,
    registration_type_input,
    set_registered_sources,
    set_source_freshness_policies,
    set_source_lifecycle_records,
    set_registration_error,
    set_registration_success,
    set_registration_validation,
    set_source_registry_error,
    source_discovery,
    source_registry_default,
):
    if register_source_button.value and registration_type_input.value == SourceType.FILE.value:
        _path_value = registration_path_input.value.strip()
        _mode_value = registration_mode_input.value
        _delimiter = registration_delimiter_input.value
        _current_signature = (_mode_value, _path_value, _delimiter)
        try:
            if source_discovery is None:
                raise ValueError("discover the source before registration")
            if discovery_signature != _current_signature:
                raise ValueError("source path, mode or delimiter changed after discovery")

            _channels = parse_channels(registration_channels_input.value)
            _common_columns = set(source_discovery.common_columns)
            _unknown_channels = tuple(
                channel for channel in _channels if channel not in _common_columns
            )
            if _unknown_channels:
                raise ValueError(
                    "mapped channels were not discovered in every CSV file: "
                    + ", ".join(_unknown_channels)
                )

            _timestamp_column = registration_timestamp_input.value.strip() or None
            if _timestamp_column is not None and _timestamp_column not in _common_columns:
                raise ValueError(
                    "timestamp column was not discovered in every CSV file: " + _timestamp_column
                )

            _sampling_rate_text = registration_sampling_rate_input.value.strip()
            _sampling_rate_hz = None if not _sampling_rate_text else float(_sampling_rate_text)
            _tolerance_text = registration_tolerance_input.value.strip()
            _tolerance = None if not _tolerance_text else float(_tolerance_text)
            _minimum_samples = int(registration_minimum_samples_input.value.strip())

            _candidate = RegisteredSource(
                source_id=registration_source_id_input.value.strip(),
                name=registration_name_input.value.strip(),
                config=FileSourceConfig(
                    source_path=_path_value,
                    asset_id=registration_asset_id_input.value.strip(),
                    measurement_point_id=(
                        registration_measurement_point_input.value.strip() or None
                    ),
                    channel_columns=_channels,
                    mode=FileSourceMode(_mode_value),
                    timestamp_column=_timestamp_column,
                    sampling_rate_hz=_sampling_rate_hz,
                    sampling_rate_tolerance_ratio=_tolerance,
                    minimum_sample_count=_minimum_samples,
                    delimiter=_delimiter,
                ),
                registered_at=datetime.now().astimezone(),
            )
            _repository = JsonSourceRepository(Path(source_registry_default))
            _validation = register_file_source(_candidate, _repository)
        except (OSError, ValueError) as error:
            set_registration_validation(None)
            set_registration_success("")
            set_registration_error(str(error))
        else:
            _sources = _repository.list_sources()
            set_registered_sources(_sources)
            set_source_lifecycle_records(
                tuple(_repository.get_lifecycle(source.source_id) for source in _sources)
            )
            set_source_freshness_policies(
                tuple(
                    _policy
                    for source in _sources
                    if (_policy := _repository.get_freshness_policy(source.source_id)) is not None
                )
            )
            set_source_registry_error("")
            set_registration_validation(_validation)
            set_registration_error("")
            set_registration_success(f"Registered source: {_candidate.source_id}")
    return


@app.cell
def _(
    mo,
    opcua_browse_result,
    opcua_browse_signature,
    registration_opcua_endpoint_input,
    registration_opcua_timeout_input,
):
    _current_signature = (
        registration_opcua_endpoint_input.value.strip(),
        registration_opcua_timeout_input.value.strip(),
    )
    opcua_browse_is_current = (
        opcua_browse_result is not None and opcua_browse_signature == _current_signature
    )
    if opcua_browse_is_current:
        opcua_browse_variables_by_label = {
            " / ".join(variable.browse_path) + f" · {variable.node_id}": variable
            for variable in opcua_browse_result.variables
        }
        opcua_browse_selection = mo.ui.multiselect(
            options=list(opcua_browse_variables_by_label),
            value=[],
            label="Variable candidates",
        )
    else:
        opcua_browse_variables_by_label = {}
        opcua_browse_selection = None
    return (
        opcua_browse_is_current,
        opcua_browse_selection,
        opcua_browse_variables_by_label,
    )


@app.cell
def _(
    JsonSourceRepository,
    OpcUaNodeMapping,
    OpcUaSourceConfig,
    Path,
    RegisteredSource,
    SourceType,
    datetime,
    opcua_browse_is_current,
    opcua_browse_selection,
    opcua_browse_variables_by_label,
    parse_opcua_node_mappings,
    register_opcua_source_button,
    registration_asset_id_input,
    registration_measurement_point_input,
    registration_name_input,
    registration_opcua_endpoint_input,
    registration_opcua_node_mappings_input,
    registration_opcua_timeout_input,
    registration_source_id_input,
    registration_type_input,
    set_registered_sources,
    set_registration_error,
    set_registration_success,
    set_registration_validation,
    set_source_freshness_policies,
    set_source_lifecycle_records,
    set_source_registry_error,
    source_registry_default,
):
    if (
        register_opcua_source_button.value
        and registration_type_input.value == SourceType.OPCUA.value
    ):
        try:
            _selected_browse_mappings = tuple(
                OpcUaNodeMapping(
                    channel_id=opcua_browse_variables_by_label[label].browse_name,
                    node_id=opcua_browse_variables_by_label[label].node_id,
                )
                for label in (
                    () if opcua_browse_selection is None else opcua_browse_selection.value
                )
            )
            _node_mappings = (
                _selected_browse_mappings
                if opcua_browse_is_current and _selected_browse_mappings
                else parse_opcua_node_mappings(registration_opcua_node_mappings_input.value)
            )
            _candidate = RegisteredSource(
                source_id=registration_source_id_input.value.strip(),
                name=registration_name_input.value.strip(),
                config=OpcUaSourceConfig(
                    endpoint_url=registration_opcua_endpoint_input.value.strip(),
                    asset_id=registration_asset_id_input.value.strip(),
                    measurement_point_id=(
                        registration_measurement_point_input.value.strip() or None
                    ),
                    node_mappings=_node_mappings,
                    timeout_seconds=float(registration_opcua_timeout_input.value.strip()),
                ),
                registered_at=datetime.now().astimezone(),
            )
            _repository = JsonSourceRepository(Path(source_registry_default))
            _repository.register(_candidate)
        except (OSError, ValueError) as error:
            set_registration_validation(None)
            set_registration_success("")
            set_registration_error(str(error))
        else:
            _sources = _repository.list_sources()
            set_registered_sources(_sources)
            set_source_lifecycle_records(
                tuple(_repository.get_lifecycle(source.source_id) for source in _sources)
            )
            set_source_freshness_policies(
                tuple(
                    _policy
                    for source in _sources
                    if (_policy := _repository.get_freshness_policy(source.source_id)) is not None
                )
            )
            set_source_registry_error("")
            set_registration_validation(None)
            set_registration_error("")
            set_registration_success(f"Registered OPC UA source: {_candidate.source_id}")
    return


@app.cell
def _(
    SourceType,
    mo,
    browse_opcua_source_button,
    discovery_signature,
    opcua_browse_error,
    opcua_browse_is_current,
    opcua_browse_result,
    opcua_browse_selection,
    registration_asset_id_input,
    registration_channels_input,
    registration_delimiter_input,
    registration_error,
    registration_measurement_point_input,
    registration_minimum_samples_input,
    registration_mode_input,
    registration_name_input,
    registration_opcua_endpoint_input,
    registration_opcua_node_mappings_input,
    registration_opcua_timeout_input,
    registration_path_input,
    registration_sampling_rate_input,
    registration_source_id_input,
    registration_success,
    registration_timestamp_input,
    registration_tolerance_input,
    registration_type_input,
    registration_validation,
    register_opcua_source_button,
    register_source_button,
    discover_source_button,
    source_discovery,
):
    def _escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
        )

    _current_signature = (
        registration_mode_input.value,
        registration_path_input.value.strip(),
        registration_delimiter_input.value,
    )
    _discovery_is_current = (
        source_discovery is not None and discovery_signature == _current_signature
    )

    if source_discovery is None:
        _discovery_view = mo.callout(
            "Enter a file or history-directory path and run discovery before mapping.",
            kind="neutral",
            title="Discover · Not run",
        )
    elif not _discovery_is_current:
        _discovery_view = mo.callout(
            "Source path, mode or delimiter changed after discovery. "
            "Discover again before registration.",
            kind="warn",
            title="Discover · Stale",
        )
    else:
        _column_labels = ", ".join(
            f"`{_escape(column)}`" for column in source_discovery.common_columns
        )
        if source_discovery.preview_rows:
            _preview_header = (
                "| "
                + " | ".join(_escape(column) for column in source_discovery.representative_columns)
                + " |"
            )
            _preview_rule = (
                "| " + " | ".join("---" for _ in source_discovery.representative_columns) + " |"
            )
            _preview_rows = tuple(
                "| " + " | ".join(_escape(value) for value in row) + " |"
                for row in source_discovery.preview_rows
            )
            _preview = mo.md(
                "#### Preview · "
                + _escape(source_discovery.representative_file)
                + "\n\n"
                + "\n".join((_preview_header, _preview_rule, *_preview_rows))
            )
        else:
            _preview = mo.callout(
                "The representative CSV contains no preview data rows.",
                kind="neutral",
                title="Preview · Empty",
            )

        _discovery_view = mo.vstack(
            [
                mo.hstack(
                    [
                        mo.stat(
                            str(source_discovery.file_count),
                            label="Discovered files",
                        ),
                        mo.stat(
                            f"{source_discovery.total_size_bytes:,} bytes",
                            label="Source bytes",
                        ),
                        mo.stat(
                            str(source_discovery.header_variant_count),
                            label="Header variants",
                        ),
                    ],
                    widths="equal",
                ),
                mo.md(f"Common columns: {_column_labels}"),
                _preview,
            ],
            gap=0.8,
        )

    if opcua_browse_error:
        _opcua_browse_view = mo.callout(
            opcua_browse_error,
            kind="danger",
            title="Browse variables · Failed",
        )
    elif opcua_browse_result is None:
        _opcua_browse_view = mo.callout(
            "Enter an endpoint and browse to discover bounded Variable candidates. "
            "No values are read.",
            kind="neutral",
            title="Browse variables · Not run",
        )
    elif not opcua_browse_is_current:
        _opcua_browse_view = mo.callout(
            "Endpoint or timeout changed after browse. Browse again before using "
            "discovered candidates.",
            kind="warn",
            title="Browse variables · Stale",
        )
    else:
        _browse_status = "TRUNCATED" if opcua_browse_result.truncated else "COMPLETE"
        _opcua_browse_view = mo.vstack(
            [
                mo.hstack(
                    [
                        mo.stat(
                            str(opcua_browse_result.visited_node_count),
                            label="Visited nodes",
                        ),
                        mo.stat(
                            str(len(opcua_browse_result.variables)),
                            label="Variable candidates",
                        ),
                        mo.stat(_browse_status, label="Browse status"),
                    ],
                    widths="equal",
                ),
                (
                    mo.callout(
                        "Node budget was reached. Results are partial; narrow the start node "
                        "in a future browse slice or use explicit NodeId mapping.",
                        kind="warn",
                        title="Browse result truncated",
                    )
                    if opcua_browse_result.truncated
                    else mo.md("Select candidate Variables to use their BrowseName as channel ID.")
                ),
                (
                    opcua_browse_selection
                    if opcua_browse_selection is not None and opcua_browse_result.variables
                    else mo.callout(
                        "No Variable candidates were discovered within the current browse bounds.",
                        kind="neutral",
                        title="Browse result · Empty",
                    )
                ),
            ],
            gap=0.6,
        )

    _is_file_registration = registration_type_input.value == SourceType.FILE.value

    if registration_error:
        _registration_status = mo.callout(
            registration_error,
            kind="danger",
            title="Registration · Failed",
        )
    elif _is_file_registration and registration_validation is not None and registration_success:
        _issue_label = (
            "none"
            if not registration_validation.quality_issue_codes
            else ", ".join(registration_validation.quality_issue_codes)
        )
        _registration_status = mo.vstack(
            [
                mo.callout(
                    registration_success,
                    kind="success",
                    title="Validate & Register · Complete",
                ),
                mo.md(
                    "| Validation fact | Value |\n"
                    "| --- | --- |\n"
                    f"| Segments | {registration_validation.segment_count:,} |\n"
                    f"| Samples | {registration_validation.total_sample_count:,} |\n"
                    f"| Data quality | {registration_validation.quality_state.value.upper()} |\n"
                    f"| Quality issues | {_issue_label} |\n"
                    f"| Source snapshots | {len(registration_validation.source_snapshots):,} |"
                ),
            ],
            gap=0.6,
        )
    elif not _is_file_registration and registration_success:
        _registration_status = mo.callout(
            registration_success,
            kind="success",
            title="Register OPC UA source · Complete",
        )
    elif _is_file_registration:
        _registration_status = mo.callout(
            "Registration validates the entire declared snapshot/history before persisting it.",
            kind="info",
            title="Validate & Register",
        )
    else:
        _registration_status = mo.callout(
            "OPC UA registration persists configuration only. Browse is a separate bounded "
            "discovery action and does not read values or claim connection health.",
            kind="info",
            title="Register · Control-plane only",
        )

    if _is_file_registration:
        registration_view = mo.vstack(
            [
                mo.md(
                    "### Add source\n\n"
                    "**1. Source** — prepared CSV file/history directory registration."
                ),
                registration_type_input,
                mo.hstack(
                    [registration_mode_input, registration_delimiter_input],
                    widths="equal",
                ),
                registration_path_input,
                discover_source_button,
                mo.md("**2. Discover & Preview**"),
                _discovery_view,
                mo.md(
                    "**3. Mapping** — Discover에서 모든 CSV에 공통으로 확인된 column을 "
                    "asset/measurement point/time/channel 의미에 명시적으로 매핑합니다."
                ),
                mo.hstack(
                    [registration_source_id_input, registration_name_input],
                    widths="equal",
                ),
                mo.hstack(
                    [registration_asset_id_input, registration_measurement_point_input],
                    widths="equal",
                ),
                registration_channels_input,
                mo.hstack(
                    [registration_timestamp_input, registration_sampling_rate_input],
                    widths="equal",
                ),
                mo.hstack(
                    [registration_tolerance_input, registration_minimum_samples_input],
                    widths="equal",
                ),
                mo.md("**4. Validate & Register**"),
                register_source_button,
                _registration_status,
            ],
            gap=0.8,
        )
    else:
        registration_view = mo.vstack(
            [
                mo.md(
                    "### Add source\n\n"
                    "**1. Source** — OPC UA endpoint와 explicit NodeId mapping을 control-plane "
                    "identity로 등록합니다."
                ),
                registration_type_input,
                mo.callout(
                    "Registration and browse are separate actions. Browse performs one bounded "
                    "anonymous session and discovers Variable identity only. Registration does "
                    "not start ingestion; bounded subscription collection is a separate runtime "
                    "action after activation, while reconnect remains unsupported.",
                    kind="neutral",
                    title="OPC UA control-plane boundary",
                ),
                mo.md("**2. Identity & endpoint**"),
                mo.hstack(
                    [registration_source_id_input, registration_name_input],
                    widths="equal",
                ),
                mo.hstack(
                    [registration_asset_id_input, registration_measurement_point_input],
                    widths="equal",
                ),
                registration_opcua_endpoint_input,
                registration_opcua_timeout_input,
                browse_opcua_source_button,
                mo.md("**3. Browse & select or provide explicit mapping**"),
                _opcua_browse_view,
                mo.md(
                    "Selected browse candidates use BrowseName as channel ID. If nothing is "
                    "selected, the explicit textarea below is used instead. 한 줄에 "
                    "`channel_id,node_id` 형식으로 입력합니다."
                ),
                registration_opcua_node_mappings_input,
                mo.md("**4. Register**"),
                register_opcua_source_button,
                _registration_status,
            ],
            gap=0.8,
        )
    return registration_view


@app.cell
def _(mo, registered_sources):
    if registered_sources:
        source_selector = mo.ui.radio(
            options=[source.source_id for source in registered_sources],
            value=registered_sources[0].source_id,
            label="Registered source",
        )
        activate_source_button = mo.ui.run_button(label="Activate source")
        pause_source_button = mo.ui.run_button(label="Pause source")
        freshness_age_input = mo.ui.text(
            value="",
            label="Max observation age (seconds)",
            placeholder="e.g. 300",
        )
        save_freshness_policy_button = mo.ui.run_button(label="Save freshness policy")
        clear_freshness_policy_button = mo.ui.run_button(label="Clear freshness policy")
        run_active_source_button = mo.ui.run_button(
            label="Run active source once",
            kind="success",
        )
        collect_opcua_subscription_button = mo.ui.run_button(
            label="Collect bounded subscription",
        )
        load_registered_source_button = mo.ui.run_button(
            label="Load registered source",
        )
        analyze_registered_source_button = mo.ui.run_button(
            label="Analyze FILE snapshot",
            kind="success",
        )
    else:
        source_selector = None
        activate_source_button = None
        pause_source_button = None
        freshness_age_input = None
        save_freshness_policy_button = None
        clear_freshness_policy_button = None
        run_active_source_button = None
        collect_opcua_subscription_button = None
        load_registered_source_button = None
        analyze_registered_source_button = None
    return (
        activate_source_button,
        analyze_registered_source_button,
        clear_freshness_policy_button,
        collect_opcua_subscription_button,
        freshness_age_input,
        load_registered_source_button,
        pause_source_button,
        run_active_source_button,
        save_freshness_policy_button,
        source_selector,
    )


@app.cell
def _(field_analysis_state_error, initial_field_analysis_results, mo):
    _initial_latest = (
        None if not initial_field_analysis_results else initial_field_analysis_results[-1]
    )
    get_field_analysis_error, set_field_analysis_error = mo.state(field_analysis_state_error)
    get_field_analysis_result, set_field_analysis_result = mo.state(_initial_latest)
    get_field_analysis_results, set_field_analysis_results = mo.state(
        initial_field_analysis_results
    )
    return (
        get_field_analysis_error,
        get_field_analysis_result,
        get_field_analysis_results,
        set_field_analysis_error,
        set_field_analysis_result,
        set_field_analysis_results,
    )


@app.cell
def _(
    get_field_analysis_error,
    get_field_analysis_result,
    get_field_analysis_results,
):
    field_analysis_error = get_field_analysis_error()
    field_analysis_result = get_field_analysis_result()
    field_analysis_results = get_field_analysis_results()
    return field_analysis_error, field_analysis_result, field_analysis_results


@app.cell
def _(
    JsonFieldFeatureAnalysisRepository,
    analyze_registered_source_button,
    field_analysis_state_path,
    registered_sources,
    run_registered_file_feature_analysis,
    set_field_analysis_error,
    set_field_analysis_result,
    set_field_analysis_results,
    source_selector,
):
    if analyze_registered_source_button is not None and analyze_registered_source_button.value:
        try:
            if source_selector is None:
                raise ValueError("select a registered source before analysis")
            _source = next(
                source for source in registered_sources if source.source_id == source_selector.value
            )
            _result = run_registered_file_feature_analysis(_source)
            _repository = JsonFieldFeatureAnalysisRepository(field_analysis_state_path)
            _repository.record(_result)
            _results = _repository.list_results()
        except (LookupError, OSError, ValueError) as error:
            set_field_analysis_error(str(error))
        else:
            set_field_analysis_result(_result)
            set_field_analysis_results(_results)
            set_field_analysis_error("")
    return


@app.cell
def _(mo):
    create_review_finding_button = mo.ui.run_button(
        label="Create review finding",
        kind="warn",
    )
    return (create_review_finding_button,)


@app.cell
def _(finding_state_error, initial_operational_findings, mo):
    get_finding_action_error, set_finding_action_error = mo.state(finding_state_error)
    get_operational_findings, set_operational_findings = mo.state(initial_operational_findings)
    return (
        get_finding_action_error,
        get_operational_findings,
        set_finding_action_error,
        set_operational_findings,
    )


@app.cell
def _(get_finding_action_error, get_operational_findings):
    finding_action_error = get_finding_action_error()
    operational_findings = get_operational_findings()
    return finding_action_error, operational_findings


@app.cell
def _(
    JsonOperationalFindingRepository,
    create_human_review_finding,
    create_review_finding_button,
    field_analysis_result,
    finding_state_path,
    set_finding_action_error,
    set_operational_findings,
):
    if create_review_finding_button.value:
        try:
            if field_analysis_result is None:
                raise ValueError("run operational FILE analysis before creating a review finding")
            _finding = create_human_review_finding(field_analysis_result)
            _repository = JsonOperationalFindingRepository(finding_state_path)
            _repository.record(_finding)
            _findings = _repository.list_findings()
        except (OSError, ValueError) as error:
            set_finding_action_error(str(error))
        else:
            set_operational_findings(_findings)
            set_finding_action_error("")
    return


@app.cell
def _(mo, operational_findings):
    if operational_findings:
        maintenance_finding_selector = mo.ui.dropdown(
            options=[finding.finding_id for finding in reversed(operational_findings)],
            value=operational_findings[-1].finding_id,
            label="Review finding",
            full_width=True,
        )
        maintenance_note_input = mo.ui.text_area(
            value="",
            label="Review note",
            rows=3,
            full_width=True,
        )
        maintenance_add_note_button = mo.ui.run_button(label="Add note")
        maintenance_acknowledge_button = mo.ui.run_button(
            label="Acknowledge",
            kind="success",
        )
        maintenance_close_button = mo.ui.run_button(
            label="Close review",
            kind="warn",
        )
    else:
        maintenance_finding_selector = None
        maintenance_note_input = None
        maintenance_add_note_button = None
        maintenance_acknowledge_button = None
        maintenance_close_button = None
    return (
        maintenance_acknowledge_button,
        maintenance_add_note_button,
        maintenance_close_button,
        maintenance_finding_selector,
        maintenance_note_input,
    )


@app.cell
def _(finding_review_state_error, initial_finding_review_events, mo):
    get_finding_review_error, set_finding_review_error = mo.state(finding_review_state_error)
    get_finding_review_events, set_finding_review_events = mo.state(initial_finding_review_events)
    return (
        get_finding_review_error,
        get_finding_review_events,
        set_finding_review_error,
        set_finding_review_events,
    )


@app.cell
def _(get_finding_review_error, get_finding_review_events):
    finding_review_error = get_finding_review_error()
    finding_review_events = get_finding_review_events()
    return finding_review_error, finding_review_events


@app.cell
def _(
    FindingReviewAction,
    JsonFindingReviewRepository,
    create_finding_review_event,
    finding_review_state_path,
    maintenance_acknowledge_button,
    maintenance_add_note_button,
    maintenance_close_button,
    maintenance_finding_selector,
    maintenance_note_input,
    operational_findings,
    set_finding_review_error,
    set_finding_review_events,
):
    _action = None
    if maintenance_add_note_button is not None and maintenance_add_note_button.value:
        _action = FindingReviewAction.NOTE
    elif maintenance_acknowledge_button is not None and maintenance_acknowledge_button.value:
        _action = FindingReviewAction.ACKNOWLEDGE
    elif maintenance_close_button is not None and maintenance_close_button.value:
        _action = FindingReviewAction.CLOSE

    if _action is not None:
        try:
            if maintenance_finding_selector is None:
                raise ValueError("select an operational finding before review action")
            _finding = next(
                finding
                for finding in operational_findings
                if finding.finding_id == maintenance_finding_selector.value
            )
            _note = "" if maintenance_note_input is None else maintenance_note_input.value
            _event = create_finding_review_event(
                _finding,
                action=_action,
                note=_note,
            )
            _repository = JsonFindingReviewRepository(finding_review_state_path)
            _repository.record(_event)
            _events = _repository.list_events()
        except (LookupError, OSError, ValueError) as error:
            set_finding_review_error(str(error))
        else:
            set_finding_review_events(_events)
            set_finding_review_error("")
    return


@app.cell
def _(mo):
    get_lifecycle_error, set_lifecycle_error = mo.state("")
    get_lifecycle_success, set_lifecycle_success = mo.state("")
    return (
        get_lifecycle_error,
        get_lifecycle_success,
        set_lifecycle_error,
        set_lifecycle_success,
    )


@app.cell
def _(get_lifecycle_error, get_lifecycle_success):
    lifecycle_error = get_lifecycle_error()
    lifecycle_success = get_lifecycle_success()
    return lifecycle_error, lifecycle_success


@app.cell
def _(
    JsonSourceRepository,
    Path,
    SourceLifecycleState,
    activate_source_button,
    datetime,
    pause_source_button,
    registered_sources,
    set_lifecycle_error,
    set_lifecycle_success,
    set_source_lifecycle_records,
    source_registry_default,
    source_selector,
    transition_source_lifecycle,
):
    _target_state = None
    if activate_source_button is not None and activate_source_button.value:
        _target_state = SourceLifecycleState.ACTIVE
    elif pause_source_button is not None and pause_source_button.value:
        _target_state = SourceLifecycleState.PAUSED

    if _target_state is not None:
        try:
            if source_selector is None:
                raise ValueError("select a registered source before changing lifecycle")
            _repository = JsonSourceRepository(Path(source_registry_default))
            _record = transition_source_lifecycle(
                _repository,
                source_selector.value,
                _target_state,
                changed_at=datetime.now().astimezone(),
            )
            _sources = _repository.list_sources()
        except (LookupError, OSError, ValueError) as error:
            set_lifecycle_success("")
            set_lifecycle_error(str(error))
        else:
            set_source_lifecycle_records(
                tuple(_repository.get_lifecycle(source.source_id) for source in _sources)
            )
            set_lifecycle_error("")
            set_lifecycle_success(
                f"Source lifecycle changed: {_record.source_id} → {_record.state.value}"
            )
    return


@app.cell
def _(mo):
    get_runtime_cycle_error, set_runtime_cycle_error = mo.state("")
    get_runtime_cycle_skipped, set_runtime_cycle_skipped = mo.state("")
    get_runtime_cycle_success, set_runtime_cycle_success = mo.state("")
    return (
        get_runtime_cycle_error,
        get_runtime_cycle_skipped,
        get_runtime_cycle_success,
        set_runtime_cycle_error,
        set_runtime_cycle_skipped,
        set_runtime_cycle_success,
    )


@app.cell
def _(
    get_runtime_cycle_error,
    get_runtime_cycle_skipped,
    get_runtime_cycle_success,
):
    runtime_cycle_error = get_runtime_cycle_error()
    runtime_cycle_skipped = get_runtime_cycle_skipped()
    runtime_cycle_success = get_runtime_cycle_success()
    return runtime_cycle_error, runtime_cycle_skipped, runtime_cycle_success


@app.cell
def _(mo):
    get_subscription_cycle_error, set_subscription_cycle_error = mo.state(None)
    get_subscription_cycle_result, set_subscription_cycle_result = mo.state(None)
    get_subscription_cycle_skipped, set_subscription_cycle_skipped = mo.state(None)
    return (
        get_subscription_cycle_error,
        get_subscription_cycle_result,
        get_subscription_cycle_skipped,
        set_subscription_cycle_error,
        set_subscription_cycle_result,
        set_subscription_cycle_skipped,
    )


@app.cell
def _(
    get_subscription_cycle_error,
    get_subscription_cycle_result,
    get_subscription_cycle_skipped,
):
    subscription_cycle_error = get_subscription_cycle_error()
    subscription_cycle_result = get_subscription_cycle_result()
    subscription_cycle_skipped = get_subscription_cycle_skipped()
    return (
        subscription_cycle_error,
        subscription_cycle_result,
        subscription_cycle_skipped,
    )


@app.cell
def _(mo):
    get_freshness_policy_error, set_freshness_policy_error = mo.state("")
    get_freshness_policy_success, set_freshness_policy_success = mo.state("")
    return (
        get_freshness_policy_error,
        get_freshness_policy_success,
        set_freshness_policy_error,
        set_freshness_policy_success,
    )


@app.cell
def _(get_freshness_policy_error, get_freshness_policy_success):
    freshness_policy_error = get_freshness_policy_error()
    freshness_policy_success = get_freshness_policy_success()
    return freshness_policy_error, freshness_policy_success


@app.cell
def _(
    JsonSourceRepository,
    Path,
    SourceFreshnessPolicy,
    clear_freshness_policy_button,
    datetime,
    freshness_age_input,
    registered_sources,
    save_freshness_policy_button,
    set_freshness_policy_error,
    set_freshness_policy_success,
    set_source_freshness_policies,
    source_registry_default,
    source_selector,
):
    _action = None
    if save_freshness_policy_button is not None and save_freshness_policy_button.value:
        _action = "save"
    elif clear_freshness_policy_button is not None and clear_freshness_policy_button.value:
        _action = "clear"

    if _action is not None:
        try:
            if source_selector is None:
                raise ValueError("select a registered source before changing freshness policy")
            _repository = JsonSourceRepository(Path(source_registry_default))
            _source_id = source_selector.value
            if _action == "save":
                if freshness_age_input is None:
                    raise ValueError("freshness policy input is unavailable")
                _raw_age = freshness_age_input.value.strip()
                if not _raw_age:
                    raise ValueError("max observation age is required")
                _policy = SourceFreshnessPolicy(
                    source_id=_source_id,
                    max_observation_age_seconds=float(_raw_age),
                    changed_at=datetime.now().astimezone(),
                )
                _repository.set_freshness_policy(_policy)
                _message = (
                    f"Freshness policy saved: {_source_id} · "
                    f"max age {_policy.max_observation_age_seconds:g} s"
                )
            else:
                _repository.clear_freshness_policy(_source_id)
                _message = f"Freshness policy cleared: {_source_id}"

            _sources = _repository.list_sources()
            _policies = tuple(
                _policy
                for source in _sources
                if (_policy := _repository.get_freshness_policy(source.source_id)) is not None
            )
        except (LookupError, OSError, ValueError) as error:
            set_freshness_policy_success("")
            set_freshness_policy_error(str(error))
        else:
            set_source_freshness_policies(_policies)
            set_freshness_policy_error("")
            set_freshness_policy_success(_message)
    return


@app.cell
def _(mo):
    get_registered_source_load_error, set_registered_source_load_error = mo.state("")
    get_registered_source_load_success, set_registered_source_load_success = mo.state("")
    return (
        get_registered_source_load_error,
        get_registered_source_load_success,
        set_registered_source_load_error,
        set_registered_source_load_success,
    )


@app.cell
def _(get_registered_source_load_error, get_registered_source_load_success):
    registered_source_load_error = get_registered_source_load_error()
    registered_source_load_success = get_registered_source_load_success()
    return registered_source_load_error, registered_source_load_success


@app.cell
def _(
    FileSourceConfig,
    OpcUaSourceConfig,
    activate_source_button,
    analyze_registered_source_button,
    assess_source_freshness,
    assess_source_health,
    clear_freshness_policy_button,
    collect_opcua_subscription_button,
    datetime,
    freshness_age_input,
    field_analysis_error,
    field_analysis_result,
    field_analysis_state_path,
    freshness_policy_error,
    freshness_policy_success,
    lifecycle_error,
    lifecycle_success,
    load_registered_source_button,
    mo,
    pause_source_button,
    run_active_source_button,
    registered_sources,
    registered_source_load_error,
    registered_source_load_success,
    registration_view,
    runtime_cycle_error,
    runtime_cycle_skipped,
    runtime_cycle_success,
    save_freshness_policy_button,
    subscription_cycle_error,
    subscription_cycle_result,
    subscription_cycle_skipped,
    source_freshness_policies,
    source_lifecycle_records,
    source_registry_default,
    source_receipt,
    source_registry_error,
    source_runtime_connection_attempts,
    source_runtime_default,
    source_runtime_error,
    source_runtime_receipts,
    source_selector,
):
    def escape_markdown_cell(value: str) -> str:
        return (
            value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
        )

    if source_registry_error:
        sources_view = mo.vstack(
            [
                mo.md("## Sources\n\n등록된 operational source control-plane record를 확인합니다."),
                registration_view,
                mo.callout(
                    source_registry_error,
                    kind="danger",
                    title="Source registry unavailable",
                ),
                mo.md(
                    f"Configured registry: `{escape_markdown_cell(source_registry_default)}`  \n"
                    f"Configured runtime state: `{escape_markdown_cell(source_runtime_default)}`"
                ),
            ],
            gap=1.2,
        )
    elif not registered_sources:
        sources_view = mo.vstack(
            [
                mo.md("## Sources\n\n등록된 operational source control-plane record를 확인합니다."),
                registration_view,
                mo.callout(
                    "No registered source exists in the configured local registry. "
                    "Use Add source above to register a prepared FILE source or an OPC UA "
                    "endpoint with explicit/browsed NodeId mapping.",
                    kind="neutral",
                    title="Registered sources · Empty",
                ),
                mo.md(f"Configured registry: `{escape_markdown_cell(source_registry_default)}`"),
            ],
            gap=1.2,
        )
    else:
        _lifecycle_by_id = {record.source_id: record for record in source_lifecycle_records}
        _freshness_policy_by_id = {policy.source_id: policy for policy in source_freshness_policies}
        _runtime_receipt_by_id = {receipt.source_id: receipt for receipt in source_runtime_receipts}
        _runtime_attempt_by_id = {
            attempt.source_id: attempt for attempt in source_runtime_connection_attempts
        }
        _rows = []
        for _source in registered_sources:
            _config = _source.config
            _mode = (
                _config.mode.value
                if isinstance(_config, FileSourceConfig)
                else "explicit-node-mapping"
            )
            _lifecycle = _lifecycle_by_id.get(_source.source_id)
            _lifecycle_state = "Unavailable" if _lifecycle is None else _lifecycle.state.value
            _rows.append(
                "| "
                + " | ".join(
                    [
                        f"`{escape_markdown_cell(_source.source_id)}`",
                        escape_markdown_cell(_source.name),
                        _source.source_type.value,
                        _mode,
                        _lifecycle_state,
                        f"`{escape_markdown_cell(_config.asset_id)}`",
                        _source.registered_at.isoformat(),
                    ]
                )
                + " |"
            )

        _selected_id = (
            registered_sources[0].source_id if source_selector is None else source_selector.value
        )
        _selected = next(
            source for source in registered_sources if source.source_id == _selected_id
        )
        _selected_config = _selected.config
        _selected_lifecycle = _lifecycle_by_id.get(_selected.source_id)
        _selected_freshness_policy = _freshness_policy_by_id.get(_selected.source_id)
        _lifecycle_state = (
            "Unavailable" if _selected_lifecycle is None else _selected_lifecycle.state.value
        )
        _lifecycle_changed_at = (
            "Unavailable"
            if _selected_lifecycle is None
            else _selected_lifecycle.changed_at.isoformat()
        )
        _lifecycle_detail = (
            "None recorded"
            if _selected_lifecycle is None or _selected_lifecycle.detail is None
            else _selected_lifecycle.detail
        )
        _measurement_point = _selected_config.measurement_point_id or "Not recorded"
        _selected_is_file = isinstance(_selected_config, FileSourceConfig)
        if _selected_is_file:
            _selected_mode = _selected_config.mode.value
            _timestamp_column = _selected_config.timestamp_column or "Not declared"
            _sampling_rate = (
                "Not declared"
                if _selected_config.sampling_rate_hz is None
                else f"{_selected_config.sampling_rate_hz:g} Hz"
            )
            _tolerance = (
                "Not declared"
                if _selected_config.sampling_rate_tolerance_ratio is None
                else f"{_selected_config.sampling_rate_tolerance_ratio:g}"
            )
            _source_specific_detail = (
                f"| Source path | `{escape_markdown_cell(_selected_config.source_path)}` |\n"
                f"| Channels | {', '.join(_selected_config.channel_columns)} |\n"
                f"| Timestamp column | `{escape_markdown_cell(_timestamp_column)}` |\n"
                f"| Sampling rate | {_sampling_rate} |\n"
                f"| Sampling-rate tolerance | {_tolerance} |\n"
                f"| Minimum samples | {_selected_config.minimum_sample_count:,} |\n"
            )
        else:
            if not isinstance(_selected_config, OpcUaSourceConfig):
                raise ValueError("unsupported registered source config")
            _selected_mode = "explicit-node-mapping"
            _node_mapping_label = ", ".join(
                f"{mapping.channel_id} → {mapping.node_id}"
                for mapping in _selected_config.node_mappings
            )
            _source_specific_detail = (
                f"| Endpoint | `{escape_markdown_cell(_selected_config.endpoint_url)}` |\n"
                f"| Node mappings | {escape_markdown_cell(_node_mapping_label)} |\n"
                f"| Request timeout | {_selected_config.timeout_seconds:g} s |\n"
            )
        _session_receipt = (
            source_receipt
            if source_receipt is not None and source_receipt.source_id == _selected.source_id
            else None
        )
        _persisted_receipt = _runtime_receipt_by_id.get(_selected.source_id)
        _selected_receipt = _session_receipt if _session_receipt is not None else _persisted_receipt
        _selected_connection_attempt = _runtime_attempt_by_id.get(_selected.source_id)
        _receipt_origin = (
            "current session"
            if _session_receipt is not None
            else "persisted latest"
            if _persisted_receipt is not None
            else "unavailable"
        )
        _freshness_policy_label = (
            "Not configured"
            if _selected_freshness_policy is None
            else f"{_selected_freshness_policy.max_observation_age_seconds:g} s"
        )
        _assessed_at = datetime.now().astimezone()
        _health = (
            None
            if _selected_lifecycle is None
            else assess_source_health(
                _selected_lifecycle,
                _selected_receipt,
                _selected_freshness_policy,
                connection_attempt=_selected_connection_attempt,
                as_of=_assessed_at,
            )
        )
        if _health is None:
            _health_evidence = mo.callout(
                "Lifecycle evidence is unavailable, so source-health dimensions cannot be "
                "assembled without inventing state.",
                kind="neutral",
                title="Source health · Unavailable",
            )
        else:
            _health_freshness = (
                "Not assessed" if _health.freshness is None else _health.freshness.state.value
            )
            _health_received = (
                "Unavailable"
                if _health.latest_received_at is None
                else _health.latest_received_at.isoformat()
            )
            _health_observed = (
                "Unavailable"
                if _health.latest_observed_at is None
                else _health.latest_observed_at.isoformat()
            )
            _health_reason = _health.reason or "None"
            _health_evidence = mo.vstack(
                [
                    mo.md(
                        "### Source health dimensions\n\n"
                        "| Dimension | Evidence state |\n"
                        "| --- | --- |\n"
                        f"| Lifecycle | {_health.lifecycle.state.value} |\n"
                        f"| Connection | {_health.connection_state.value} |\n"
                        f"| Data flow | {_health.data_flow_state.value} |\n"
                        f"| Freshness | {_health_freshness} |\n"
                        f"| Latest observed_at | {_health_observed} |\n"
                        f"| Latest received_at | {_health_received} |\n"
                        f"| Reason | {escape_markdown_cell(_health_reason)} |\n"
                        f"| Assessed at | {_health.assessed_at.isoformat()} |"
                    ),
                    mo.callout(
                        "This is a multidimensional read model, not a single healthy/unhealthy "
                        "verdict. Latest bounded attempt evidence is historical only; it does not "
                        "provide current/session connection telemetry, so connection remains "
                        "NOT_INSTRUMENTED.",
                        kind="info",
                        title="Health semantics",
                    ),
                ],
                gap=0.6,
            )

        if _selected_connection_attempt is None:
            _connection_attempt_evidence = mo.callout(
                "No bounded connector/session attempt evidence is recorded for this source.",
                kind="neutral",
                title="Latest connection attempt · Unavailable",
            )
        else:
            _attempt_connected = (
                "Unavailable"
                if _selected_connection_attempt.connected_at is None
                else _selected_connection_attempt.connected_at.isoformat()
            )
            _attempt_detail = _selected_connection_attempt.detail or "None"
            _attempted_at_label = _selected_connection_attempt.attempted_at.isoformat()
            _completed_at_label = _selected_connection_attempt.completed_at.isoformat()
            _connection_attempt_evidence = mo.vstack(
                [
                    mo.md(
                        "### Latest connection attempt\n\n"
                        "| Attempt fact | Value |\n"
                        "| --- | --- |\n"
                        f"| Operation | {_selected_connection_attempt.operation.value} |\n"
                        f"| Outcome | {_selected_connection_attempt.outcome.value.upper()} |\n"
                        f"| Attempted at | {_attempted_at_label} |\n"
                        f"| Connected at | {_attempt_connected} |\n"
                        f"| Completed at | {_completed_at_label} |\n"
                        f"| Detail | {escape_markdown_cell(_attempt_detail)} |"
                    ),
                    mo.callout(
                        "This is the latest bounded historical attempt, not current connection "
                        "state. Operation identifies which runtime produced the evidence; a "
                        "successful attempt does not mean the source remains connected after "
                        "the bounded cycle.",
                        kind="info",
                        title="Connection-attempt semantics",
                    ),
                ],
                gap=0.6,
            )

        _selected_subscription_result = (
            subscription_cycle_result
            if subscription_cycle_result is not None
            and subscription_cycle_result.source_id == _selected.source_id
            else None
        )
        _selected_subscription_error = (
            subscription_cycle_error[1]
            if subscription_cycle_error is not None
            and subscription_cycle_error[0] == _selected.source_id
            else ""
        )
        _selected_subscription_skipped = (
            subscription_cycle_skipped[1]
            if subscription_cycle_skipped is not None
            and subscription_cycle_skipped[0] == _selected.source_id
            else ""
        )
        if _selected_is_file:
            _subscription_runtime_evidence = mo.callout(
                "Bounded DataChange collection is available only for registered OPC UA sources.",
                kind="neutral",
                title="Bounded subscription · Not applicable",
            )
        elif _selected_subscription_result is None:
            if _selected_subscription_error:
                _subscription_runtime_evidence = mo.callout(
                    _selected_subscription_error,
                    kind="danger",
                    title="Bounded subscription failed",
                )
            elif _selected_subscription_skipped:
                _subscription_runtime_evidence = mo.callout(
                    _selected_subscription_skipped,
                    kind="neutral",
                    title="Bounded subscription skipped",
                )
            else:
                _subscription_runtime_evidence = mo.callout(
                    "No bounded subscription has been collected for this source in the current "
                    "Operations session. The action runs only while lifecycle is ACTIVE.",
                    kind="neutral",
                    title="Bounded subscription · Not run",
                )
        else:
            _subscription = _selected_subscription_result.subscription
            if _subscription is None:
                _subscription_runtime_evidence = mo.callout(
                    _selected_subscription_error or "No subscription result was produced.",
                    kind="danger",
                    title="Bounded subscription failed",
                )
            else:
                _connector_result = _subscription.subscription
                _coverage = _subscription.coverage
                _observed_channels = (
                    ", ".join(_coverage.observed_channel_ids)
                    if _coverage.observed_channel_ids
                    else "None"
                )
                _missing_channels = (
                    ", ".join(_coverage.missing_channel_ids)
                    if _coverage.missing_channel_ids
                    else "None"
                )
                _event_rows = []
                for _event in _subscription.events:
                    _observation = _event.notification.observation
                    _event_value = (
                        "Unavailable" if _observation.value is None else f"{_observation.value:g}"
                    )
                    _source_timestamp = (
                        "Unavailable"
                        if _observation.source_timestamp is None
                        else _observation.source_timestamp.isoformat()
                    )
                    _event_rows.append(
                        "| "
                        + " | ".join(
                            [
                                str(_event.collection_index),
                                escape_markdown_cell(_event.channel_id),
                                _event_value,
                                escape_markdown_cell(_observation.status_text),
                                _source_timestamp,
                                _observation.received_at.isoformat(),
                                "yes" if _event.notification.replayed else "no",
                            ]
                        )
                        + " |"
                    )
                _coverage_kind = "success" if _coverage.has_full_channel_coverage else "warn"
                _subscription_runtime_evidence = mo.vstack(
                    [
                        (
                            mo.callout(
                                _selected_subscription_error,
                                kind="danger",
                                title="Bounded subscription runtime evidence persistence failed",
                            )
                            if _selected_subscription_error
                            else mo.callout(
                                "The bounded subscription cycle completed. Coverage means only "
                                "that each registered channel appeared at least once; it is not "
                                "a synchronized snapshot or analysis-ready window.",
                                kind=_coverage_kind,
                                title="Bounded subscription collected",
                            )
                        ),
                        mo.md(
                            "| Collection fact | Value |\n"
                            "| --- | --- |\n"
                            f"| Completion reason | {_connector_result.completion_reason.value} |\n"
                            f"| Notifications | {_coverage.notification_count} |\n"
                            "| Configured channels | "
                            f"{', '.join(_coverage.configured_channel_ids)} |\n"
                            f"| Observed channels | {_observed_channels} |\n"
                            f"| Missing channels | {_missing_channels} |\n"
                            f"| Full registered-channel coverage | "
                            f"{'yes' if _coverage.has_full_channel_coverage else 'no'} |\n"
                            f"| Connected at | {_connector_result.connected_at.isoformat()} |\n"
                            f"| Completed at | {_connector_result.completed_at.isoformat()} |"
                        ),
                        mo.md(
                            "#### Collected events\n\n"
                            "| # | Channel | Value | OPC UA status | Source timestamp | "
                            "Received at | Replayed |\n"
                            "| ---: | --- | ---: | --- | --- | --- | --- |\n"
                            + "\n".join(_event_rows)
                        ),
                    ],
                    gap=0.6,
                )

        if _selected_receipt is None:
            _receipt_evidence = mo.callout(
                "No platform receipt-time evidence has been recorded for this selected source. "
                "Freshness cannot be assessed until a supported runtime produces accepted "
                "observation receipt timing evidence.",
                kind="neutral",
                title="Receipt timing · Unavailable",
            )
            _freshness_evidence = mo.callout(
                f"Configured max observation age: {_freshness_policy_label}. "
                "No current receipt evidence is available for assessment.",
                kind="neutral",
                title="Freshness · Unavailable",
            )
        else:
            _lag = _selected_receipt.lag_seconds
            _lag_label = (
                f"{_lag:+.3f} s"
                if _lag is not None
                else f"Unavailable · {_selected_receipt.lag_unavailable_reason}"
            )
            _observed_label = (
                "Unavailable"
                if _selected_receipt.observed_at is None
                else _selected_receipt.observed_at.isoformat()
            )
            _freshness = assess_source_freshness(
                _selected_receipt,
                _selected_freshness_policy,
                as_of=_assessed_at,
            )
            _age_label = (
                "Unavailable"
                if _freshness.observation_age_seconds is None
                else f"{_freshness.observation_age_seconds:+.3f} s"
            )
            _freshness_reason = "" if _freshness.reason is None else f" · {_freshness.reason}"
            _receipt_evidence = mo.vstack(
                [
                    mo.md(
                        "### Receipt timing\n\n"
                        "| Timing fact | Value |\n"
                        "| --- | --- |\n"
                        f"| Latest observed_at | {_observed_label} |\n"
                        f"| received_at | {_selected_receipt.received_at.isoformat()} |\n"
                        f"| observed→received delivery lag | {_lag_label} |\n"
                        f"| Receipt state | {_receipt_origin} |"
                    ),
                    mo.callout(
                        (
                            "received_at is the time this prepared source load was accepted after "
                            "validation. It is not reconstructed sensor transport arrival time."
                            if _selected_is_file
                            else "received_at is the platform acceptance time after the one-shot "
                            "OPC UA snapshot completed. It does not imply continuous transport "
                            "arrival or a persistent connection."
                        ),
                        kind="info",
                        title="Timing semantics",
                    ),
                ],
                gap=0.6,
            )
            _freshness_evidence = mo.callout(
                f"State: {_freshness.state.value.upper()} · "
                f"observation age: {_age_label} · "
                f"max age: {_freshness_policy_label} · "
                f"assessed at: {_freshness.assessed_at.isoformat()}"
                f"{_freshness_reason}",
                kind=(
                    "success"
                    if _freshness.state.value == "fresh"
                    else "warn"
                    if _freshness.state.value == "stale"
                    else "neutral"
                ),
                title=f"Freshness · {_freshness.state.value}",
            )

        sources_view = mo.vstack(
            [
                mo.md(
                    "## Sources\n\n"
                    "재시작 후에도 보존되는 source registration control-plane record를 "
                    "목록과 상세 설정으로 확인합니다."
                ),
                registration_view,
                mo.hstack(
                    [
                        mo.stat(
                            str(len(registered_sources)),
                            label="Registered sources",
                            caption="Persistent control-plane records",
                        ),
                        mo.stat(
                            str(
                                sum(
                                    record.state.value == "active"
                                    for record in source_lifecycle_records
                                )
                            ),
                            label="Active intent",
                            caption="Administrative state, not connection proof",
                        ),
                        mo.stat(
                            "Not instrumented",
                            label="Connection health",
                            caption="Registration does not imply connectivity",
                        ),
                        mo.stat(
                            "On-demand",
                            label="Runtime actions",
                            caption="FILE/OPC UA bounded execution",
                        ),
                    ],
                    widths="equal",
                ),
                mo.md(
                    "| Source ID | Name | Type | Mode | Lifecycle | Asset | Registered at |\n"
                    "| --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(_rows)
                ),
                source_selector,
                mo.md(
                    "### Source detail\n\n"
                    "| Field | Registered value |\n"
                    "| --- | --- |\n"
                    f"| Source ID | `{escape_markdown_cell(_selected.source_id)}` |\n"
                    f"| Name | {escape_markdown_cell(_selected.name)} |\n"
                    f"| Type | {_selected.source_type.value} |\n"
                    f"| Mode | {_selected_mode} |\n"
                    f"| Lifecycle | {_lifecycle_state} |\n"
                    f"| Lifecycle changed at | {_lifecycle_changed_at} |\n"
                    f"| Lifecycle detail | {escape_markdown_cell(_lifecycle_detail)} |\n"
                    f"| Asset | `{escape_markdown_cell(_selected_config.asset_id)}` |\n"
                    f"| Measurement point | `{escape_markdown_cell(_measurement_point)}` |\n"
                    f"{_source_specific_detail}"
                    f"| Registered at | {_selected.registered_at.isoformat()} |"
                ),
                mo.md("### Lifecycle control"),
                mo.hstack(
                    [activate_source_button, pause_source_button],
                    widths="equal",
                ),
                (
                    mo.callout(
                        lifecycle_error,
                        kind="danger",
                        title="Lifecycle transition failed",
                    )
                    if lifecycle_error
                    else (
                        mo.callout(
                            lifecycle_success,
                            kind="success",
                            title="Lifecycle updated",
                        )
                        if lifecycle_success
                        else mo.callout(
                            "REGISTERED/ACTIVE/PAUSED/ERROR is administrative control-plane "
                            "state. ACTIVE means enabled for a runtime to consume; it does not "
                            "prove that a connection exists or that ingestion is running.",
                            kind="info",
                            title="Lifecycle semantics",
                        )
                    )
                ),
                mo.md("### Runtime execution"),
                mo.md("#### One-shot observation"),
                run_active_source_button,
                (
                    mo.callout(
                        runtime_cycle_error,
                        kind="danger",
                        title="Runtime cycle failed",
                    )
                    if runtime_cycle_error
                    else (
                        mo.callout(
                            runtime_cycle_skipped,
                            kind="neutral",
                            title="Runtime cycle skipped",
                        )
                        if runtime_cycle_skipped
                        else (
                            mo.callout(
                                runtime_cycle_success,
                                kind="success",
                                title="Runtime cycle succeeded",
                            )
                            if runtime_cycle_success
                            else mo.callout(
                                "Run active source once dispatches to the selected source type. "
                                "FILE re-validates current bytes; OPC UA performs one explicit "
                                "connect/read/disconnect. Both record latest receipt evidence and "
                                "leave lifecycle ACTIVE on success. Source-owned failures may "
                                "transition ACTIVE → ERROR while platform failures keep lifecycle "
                                "ACTIVE. This is one explicit iteration, not background polling.",
                                kind="info",
                                title="Runtime cycle semantics",
                            )
                        )
                    )
                ),
                mo.md("#### Bounded OPC UA subscription"),
                (
                    _subscription_runtime_evidence
                    if _selected_is_file
                    else mo.vstack(
                        [
                            collect_opcua_subscription_button,
                            mo.callout(
                                "Collects one bounded DataChange session with a 5 s collection "
                                "timeout, 500 ms publishing interval and max events equal to the "
                                "registered channel count. It records latest connection-attempt "
                                "evidence only; receipt/freshness is not updated.",
                                kind="info",
                                title="Bounded collection semantics",
                            ),
                            _subscription_runtime_evidence,
                        ],
                        gap=0.6,
                    )
                ),
                mo.md("### Freshness policy"),
                mo.md(f"Current max observation age: **{_freshness_policy_label}**"),
                freshness_age_input,
                mo.hstack(
                    [save_freshness_policy_button, clear_freshness_policy_button],
                    widths="equal",
                ),
                (
                    mo.callout(
                        freshness_policy_error,
                        kind="danger",
                        title="Freshness policy update failed",
                    )
                    if freshness_policy_error
                    else (
                        mo.callout(
                            freshness_policy_success,
                            kind="success",
                            title="Freshness policy updated",
                        )
                        if freshness_policy_success
                        else mo.callout(
                            "Freshness policy is source-specific and defines the maximum allowed "
                            "age of the latest observation at assessment time. It does not use "
                            "delivery lag as the freshness age.",
                            kind="info",
                            title="Freshness semantics",
                        )
                    )
                ),
                mo.md("### Analyze current FILE snapshot"),
                (
                    mo.vstack(
                        [
                            analyze_registered_source_button,
                            (
                                mo.callout(
                                    field_analysis_error,
                                    kind="danger",
                                    title="Operational analysis failed",
                                )
                                if field_analysis_error
                                else (
                                    mo.callout(
                                        f"AnalysisRun created: "
                                        f"`{field_analysis_result.run.analysis_run_id}` · "
                                        f"{len(field_analysis_result.evidence.values)} "
                                        f"vibration feature values · saved to "
                                        f"`{field_analysis_state_path}`",
                                        kind="success",
                                        title="Operational feature analysis completed",
                                    )
                                    if field_analysis_result is not None
                                    and field_analysis_result.run.source_id == _selected.source_id
                                    else mo.callout(
                                        "Runs the registered FILE snapshot through the existing "
                                        "CSV adapter and vibration-statistical-v1 "
                                        "feature extractor. "
                                        "The result is persisted as operational analysis history. "
                                        "It is still AnalysisRun plus feature evidence only; "
                                        "it does not create a finding or health state.",
                                        kind="info",
                                        title="Operational analysis semantics",
                                    )
                                )
                            ),
                        ],
                        gap=0.6,
                    )
                    if _selected_is_file and _selected_config.mode.value == "snapshot"
                    else mo.callout(
                        "The first operational producer supports registered FILE snapshot mode "
                        "with explicit timezone-aware source timestamps. History-directory and "
                        "OPC UA analysis remain unavailable.",
                        kind="neutral",
                        title="Operational analysis · Unsupported for selected source",
                    )
                ),
                mo.md("### Load current observation"),
                (
                    load_registered_source_button
                    if _selected_is_file
                    else mo.callout(
                        "Registered OPC UA source has no separate manual loader. Use Run active "
                        "source once to read the configured nodes and project one canonical "
                        "AssetObservationSummary from that bounded snapshot.",
                        kind="neutral",
                        title="OPC UA observation load · Unavailable",
                    )
                ),
                (
                    mo.callout(
                        registered_source_load_error,
                        kind="danger",
                        title="Registered source load failed",
                    )
                    if registered_source_load_error
                    else (
                        mo.callout(
                            registered_source_load_success,
                            kind="success",
                            title="Registered source observation loaded",
                        )
                        if registered_source_load_success
                        else mo.callout(
                            "Load re-validates the source bytes currently available at the "
                            "registered path and projects them through the existing observation "
                            "boundary. It does not start continuous ingestion.",
                            kind="info",
                            title="On-demand observation load",
                        )
                    )
                    if _selected_is_file
                    else mo.callout(
                        "OPC UA observation summary is produced by the one-shot runtime action, "
                        "not by this FILE-only manual load action.",
                        kind="neutral",
                        title="Observation evidence · Unavailable",
                    )
                ),
                (
                    mo.callout(
                        source_runtime_error,
                        kind="danger",
                        title="Source runtime state unavailable",
                    )
                    if source_runtime_error
                    else mo.callout(
                        "Latest receipt and bounded connection-attempt evidence are persisted "
                        "separately from the source registry. Current connection status, "
                        "retry/buffer state and receipt/attempt history are not stored.",
                        kind="info",
                        title="Runtime evidence persistence",
                    )
                ),
                _connection_attempt_evidence,
                _health_evidence,
                _receipt_evidence,
                _freshness_evidence,
                mo.callout(
                    "Freshness is a timing-policy assessment only. Registration, lifecycle "
                    "intent and on-demand loading still do not label a source online, healthy "
                    "or actively ingested. Connection/ingestion health requires separate "
                    "runtime and telemetry evidence.",
                    kind="info",
                    title="Runtime boundary",
                ),
                mo.md(
                    f"Configured registry: `{escape_markdown_cell(source_registry_default)}`  \n"
                    f"Configured runtime state: `{escape_markdown_cell(source_runtime_default)}`"
                ),
            ],
            gap=1.2,
        )
    return sources_view


@app.cell
def _(initial_error, initial_summary, initial_timeline, mo):
    get_observation, set_observation = mo.state(initial_summary)
    get_timeline, set_timeline = mo.state(initial_timeline)
    get_load_error, set_load_error = mo.state(initial_error)
    get_source_receipt, set_source_receipt = mo.state(None)
    return (
        get_load_error,
        get_observation,
        get_source_receipt,
        get_timeline,
        set_load_error,
        set_observation,
        set_source_receipt,
        set_timeline,
    )


@app.cell
def _(
    FileSourceConfig,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    Path,
    SourceRuntimeCycleState,
    ThreadPoolExecutor,
    asyncio,
    project_registered_opcua_observation_summary,
    run_active_source_button,
    run_registered_file_source_cycle,
    run_registered_opcua_source_cycle,
    set_load_error,
    set_observation,
    set_runtime_cycle_error,
    set_runtime_cycle_skipped,
    set_runtime_cycle_success,
    set_source_lifecycle_records,
    set_source_receipt,
    set_source_runtime_connection_attempts,
    set_source_runtime_error,
    set_source_runtime_receipts,
    set_timeline,
    source_registry_default,
    source_runtime_default,
    source_selector,
    validate_distinct_source_state_paths,
):
    if run_active_source_button is not None and run_active_source_button.value:
        try:
            if source_selector is None:
                raise ValueError("select a registered source before running a runtime cycle")
            _registry_path = Path(source_registry_default)
            _runtime_path = Path(source_runtime_default)
            validate_distinct_source_state_paths(_registry_path, _runtime_path)
            _source_repository = JsonSourceRepository(_registry_path)
            _runtime_repository = JsonSourceRuntimeRepository(_runtime_path)
            _source = _source_repository.get(source_selector.value)
            if isinstance(_source.config, FileSourceConfig):
                _result = run_registered_file_source_cycle(
                    _source_repository,
                    _source_repository,
                    _runtime_repository,
                    _source.source_id,
                )
            elif isinstance(_source.config, OpcUaSourceConfig):

                def _run_opcua_cycle():
                    return asyncio.run(
                        run_registered_opcua_source_cycle(
                            _source_repository,
                            _source_repository,
                            _runtime_repository,
                            _source.source_id,
                        )
                    )

                with ThreadPoolExecutor(max_workers=1) as _executor:
                    _result = _executor.submit(_run_opcua_cycle).result()
            else:
                raise ValueError("unsupported registered source config")
            _sources = _source_repository.list_sources()
            _lifecycle_records = tuple(
                _source_repository.get_lifecycle(source.source_id) for source in _sources
            )
        except (LookupError, OSError, ValueError) as error:
            set_runtime_cycle_success("")
            set_runtime_cycle_skipped("")
            set_runtime_cycle_error(str(error))
        else:
            set_source_lifecycle_records(_lifecycle_records)
            if _result.state == SourceRuntimeCycleState.SUCCEEDED:
                _received = _result.received
                if _received is None:
                    set_runtime_cycle_success("")
                    set_runtime_cycle_skipped("")
                    set_runtime_cycle_error(
                        "runtime cycle invariant violation: succeeded result has no observation"
                    )
                else:
                    _loaded = _received.observation
                    if isinstance(_source.config, FileSourceConfig):
                        set_observation(_loaded.latest)
                        set_timeline(_loaded.timeline)
                    else:
                        set_observation(project_registered_opcua_observation_summary(_loaded))
                        set_timeline(None)
                    set_source_receipt(_received.receipt)
                    set_load_error("")
                    set_runtime_cycle_error("")
                    set_runtime_cycle_skipped("")
                    _projection_note = (
                        ""
                        if isinstance(_source.config, FileSourceConfig)
                        else " · canonical one-shot observation projected"
                    )
                    set_runtime_cycle_success(
                        f"Runtime cycle succeeded: {_result.source_id} · "
                        f"received {_received.receipt.received_at.isoformat()}"
                        f"{_projection_note}"
                    )
            elif _result.state == SourceRuntimeCycleState.SKIPPED:
                set_runtime_cycle_error("")
                set_runtime_cycle_success("")
                set_runtime_cycle_skipped(_result.message or "runtime cycle skipped")
            else:
                set_runtime_cycle_success("")
                set_runtime_cycle_skipped("")
                _scope = "unknown" if _result.failure_scope is None else _result.failure_scope.value
                set_runtime_cycle_error(
                    f"{_scope} failure · {_result.message or 'runtime cycle failed'}"
                )

            try:
                _registered_ids = {source.source_id for source in _sources}
                _runtime_receipts = tuple(
                    receipt
                    for receipt in _runtime_repository.list_latest_receipts()
                    if receipt.source_id in _registered_ids
                )
                _runtime_connection_attempts = tuple(
                    attempt
                    for attempt in _runtime_repository.list_latest_connection_attempts()
                    if attempt.source_id in _registered_ids
                )
            except (OSError, ValueError) as error:
                set_source_runtime_error(str(error))
            else:
                set_source_runtime_connection_attempts(_runtime_connection_attempts)
                set_source_runtime_receipts(_runtime_receipts)
                set_source_runtime_error("")
    return


@app.cell
def _(
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    Path,
    SourceRuntimeCycleState,
    ThreadPoolExecutor,
    asyncio,
    collect_opcua_subscription_button,
    run_registered_opcua_subscription_cycle,
    set_source_lifecycle_records,
    set_source_runtime_connection_attempts,
    set_source_runtime_error,
    set_subscription_cycle_error,
    set_subscription_cycle_result,
    set_subscription_cycle_skipped,
    source_registry_default,
    source_runtime_default,
    source_selector,
    validate_distinct_source_state_paths,
):
    if collect_opcua_subscription_button is not None and collect_opcua_subscription_button.value:
        _selected_source_id = None
        try:
            if source_selector is None:
                raise ValueError(
                    "select a registered OPC UA source before collecting a subscription"
                )
            _selected_source_id = source_selector.value
            _registry_path = Path(source_registry_default)
            _runtime_path = Path(source_runtime_default)
            validate_distinct_source_state_paths(_registry_path, _runtime_path)
            _source_repository = JsonSourceRepository(_registry_path)
            _runtime_repository = JsonSourceRuntimeRepository(_runtime_path)
            _source = _source_repository.get(_selected_source_id)
            if not isinstance(_source.config, OpcUaSourceConfig):
                raise ValueError(
                    "bounded subscription collection is available only for OPC UA sources"
                )
            _max_events = max(1, len(_source.config.node_mappings))

            def _run_subscription_cycle():
                return asyncio.run(
                    run_registered_opcua_subscription_cycle(
                        _source_repository,
                        _source_repository,
                        _runtime_repository,
                        _source.source_id,
                        publishing_interval_ms=500.0,
                        collection_timeout_seconds=5.0,
                        max_events=_max_events,
                        queue_maxsize=128,
                    )
                )

            with ThreadPoolExecutor(max_workers=1) as _executor:
                _result = _executor.submit(_run_subscription_cycle).result()

            _sources = _source_repository.list_sources()
            _lifecycle_records = tuple(
                _source_repository.get_lifecycle(source.source_id) for source in _sources
            )
        except (LookupError, OSError, ValueError) as error:
            set_subscription_cycle_result(None)
            set_subscription_cycle_skipped(None)
            set_subscription_cycle_error(
                (
                    "" if _selected_source_id is None else _selected_source_id,
                    str(error),
                )
            )
        else:
            set_source_lifecycle_records(_lifecycle_records)
            if _result.state == SourceRuntimeCycleState.SUCCEEDED:
                set_subscription_cycle_result(_result)
                set_subscription_cycle_error(None)
                set_subscription_cycle_skipped(None)
            elif _result.state == SourceRuntimeCycleState.SKIPPED:
                set_subscription_cycle_result(None)
                set_subscription_cycle_error(None)
                set_subscription_cycle_skipped(
                    (
                        _result.source_id,
                        _result.message or "bounded subscription cycle skipped",
                    )
                )
            else:
                _scope = "unknown" if _result.failure_scope is None else _result.failure_scope.value
                set_subscription_cycle_result(_result)
                set_subscription_cycle_skipped(None)
                set_subscription_cycle_error(
                    (
                        _result.source_id,
                        f"{_scope} failure · "
                        f"{_result.message or 'bounded subscription cycle failed'}",
                    )
                )

            try:
                _registered_ids = {source.source_id for source in _sources}
                _runtime_connection_attempts = tuple(
                    attempt
                    for attempt in _runtime_repository.list_latest_connection_attempts()
                    if attempt.source_id in _registered_ids
                )
            except (OSError, ValueError) as error:
                set_source_runtime_error(str(error))
            else:
                set_source_runtime_connection_attempts(_runtime_connection_attempts)
                set_source_runtime_error("")
    return


@app.cell
def _(
    FileSourceConfig,
    JsonSourceRuntimeRepository,
    Path,
    load_registered_source_button,
    receive_registered_file_source_observation,
    registered_sources,
    set_load_error,
    set_observation,
    set_registered_source_load_error,
    set_registered_source_load_success,
    set_source_receipt,
    set_source_runtime_error,
    set_source_runtime_receipts,
    set_timeline,
    source_registry_default,
    source_runtime_default,
    source_selector,
    validate_distinct_source_state_paths,
):
    if load_registered_source_button is not None and load_registered_source_button.value:
        try:
            if source_selector is None:
                raise ValueError("select a registered source before loading")
            _selected = next(
                source for source in registered_sources if source.source_id == source_selector.value
            )
            if not isinstance(_selected.config, FileSourceConfig):
                raise ValueError(
                    "on-demand observation load currently supports registered file sources only"
                )
            _received = receive_registered_file_source_observation(_selected)
            _loaded = _received.observation
        except (OSError, ValueError) as error:
            set_observation(None)
            set_timeline(None)
            set_source_receipt(None)
            set_load_error(str(error))
            set_registered_source_load_success("")
            set_registered_source_load_error(str(error))
        else:
            set_observation(_loaded.latest)
            set_timeline(_loaded.timeline)
            set_source_receipt(_received.receipt)
            set_load_error("")
            set_registered_source_load_error("")
            set_registered_source_load_success(
                f"Loaded current observation from registered source: {_selected.source_id}"
            )
            try:
                _registry_path = Path(source_registry_default)
                _runtime_path = Path(source_runtime_default)
                validate_distinct_source_state_paths(_registry_path, _runtime_path)
                _runtime_repository = JsonSourceRuntimeRepository(_runtime_path)
                _runtime_repository.record_receipt(_received.receipt)
                _registered_ids = {source.source_id for source in registered_sources}
                _runtime_receipts = tuple(
                    receipt
                    for receipt in _runtime_repository.list_latest_receipts()
                    if receipt.source_id in _registered_ids
                )
            except (OSError, ValueError) as error:
                set_source_runtime_error(str(error))
            else:
                set_source_runtime_receipts(_runtime_receipts)
                set_source_runtime_error("")
    return


@app.cell
def _(
    asset_input,
    channels_input,
    history_directory_input,
    load_button,
    load_observation,
    measurement_point_input,
    sampling_rate_input,
    set_load_error,
    set_observation,
    set_source_receipt,
    set_timeline,
    source_id_input,
    source_input,
    timestamp_input,
):
    if load_button.value:
        _summary, _timeline, _error = load_observation(
            source_path=source_input.value,
            history_directory=history_directory_input.value,
            asset_id=asset_input.value,
            source_id=source_id_input.value,
            measurement_point_id=measurement_point_input.value,
            channels=channels_input.value,
            timestamp_column=timestamp_input.value,
            sampling_rate_hz=sampling_rate_input.value,
        )
        set_observation(_summary)
        set_timeline(_timeline)
        set_source_receipt(None)
        set_load_error(_error)
    return


@app.cell
def _(get_load_error, get_observation, get_source_receipt, get_timeline):
    observation = get_observation()
    source_receipt = get_source_receipt()
    timeline = get_timeline()
    load_error = get_load_error()
    return load_error, observation, source_receipt, timeline


@app.cell
def _(DataQualityState, mo, observation, operational_findings):
    if observation is None:
        asset_label = "Not connected"
        last_observed_label = "Unavailable"
        quality_label = "Unavailable"
        quality_caption = "Load or run a supported source"
    else:
        asset_label = observation.asset_id
        last_observed_label = (
            "Unavailable"
            if observation.observed_end_at is None
            else observation.observed_end_at.isoformat()
        )
        quality_label = observation.data_quality.state.value.upper()
        quality_caption = (
            "No recorded source-quality issue"
            if observation.data_quality.state == DataQualityState.PASS
            else ", ".join(observation.data_quality.issue_codes)
        )

    overview_stats = mo.hstack(
        [
            mo.stat(asset_label, label="Asset", caption="Operational identity"),
            mo.stat(
                last_observed_label,
                label="Last observed",
                caption="Recorded source time, not platform receipt time",
            ),
            mo.stat(
                quality_label,
                label="Data quality",
                caption=quality_caption,
            ),
            mo.stat(
                str(len(operational_findings)),
                label="Review findings",
                caption=(
                    "No explicit human review request recorded"
                    if not operational_findings
                    else "Explicit REVIEW_REQUIRED workflow requests"
                ),
            ),
        ],
        widths="equal",
    )
    return overview_stats


@app.cell
def _(load_error, mo, observation, timeline):
    if load_error:
        connection_status = mo.callout(
            load_error,
            kind="danger",
            title="Source validation failed",
        )
    elif observation is None:
        connection_status = mo.callout(
            "No operational observation is loaded. The Operations structure remains visible so "
            "missing capabilities are explicit rather than hidden.",
            kind="neutral",
            title="Observation unavailable",
        )
    elif timeline is not None:
        connection_status = mo.callout(
            f"{timeline.segment_count} prepared field segments loaded and ordered by "
            "their recorded timestamps. The latest segment is used for current "
            "observation details; the timeline itself does not imply a PHM trend.",
            kind="success",
            title="Observation history loaded",
        )
    else:
        connection_status = mo.callout(
            "Operational observation loaded through the application boundary. "
            "This confirms source identity and recorded quality only; it does not "
            "declare the asset healthy or unhealthy.",
            kind="success",
            title="Observation source loaded",
        )
    return connection_status


@app.cell
def _(mo, observation):
    if observation is None:
        observation_detail = mo.callout(
            "Observation identity, time range, channels and sample population will appear "
            "here after a supported source is loaded or run.",
            kind="neutral",
            title="Observation unavailable",
        )
    else:
        _start = (
            "Unavailable"
            if observation.observed_start_at is None
            else observation.observed_start_at.isoformat()
        )
        _end = (
            "Unavailable"
            if observation.observed_end_at is None
            else observation.observed_end_at.isoformat()
        )
        _sampling_rate = (
            "Not declared"
            if observation.sampling_rate_hz is None
            else f"{observation.sampling_rate_hz:g} Hz"
        )
        observation_detail = mo.md(
            "### Observation\n\n"
            "| Field | Value |\n"
            "| --- | --- |\n"
            f"| Asset | `{observation.asset_id}` |\n"
            f"| Measurement point | `{observation.measurement_point_id or 'Not recorded'}` |\n"
            f"| Source | `{observation.source_id}` |\n"
            f"| Observed start | {_start} |\n"
            f"| Observed end | {_end} |\n"
            f"| Samples | {observation.sample_count:,} |\n"
            f"| Channels | {', '.join(observation.channels)} |\n"
            f"| Sampling rate | {_sampling_rate} |"
        )
    return observation_detail


@app.cell
def _(mo, observation):
    if observation is None:
        quality_view = mo.callout(
            "No data-quality assessment is available until a source is validated.",
            kind="neutral",
            title="Data Quality · Unavailable",
        )
    elif not observation.data_quality.issues:
        quality_view = mo.callout(
            "The current observation has no recorded data-quality issue under its source "
            "boundary checks.",
            kind="success",
            title="Data Quality · PASS",
        )
    else:
        _rows = "\n".join(
            f"| {issue.severity.value} | `{issue.code}` | {issue.message} |"
            for issue in observation.data_quality.issues
        )
        quality_view = mo.vstack(
            [
                mo.callout(
                    "Recorded quality issues are shown without automatic repair, "
                    "resampling or imputation.",
                    kind="warn",
                    title=f"Data Quality · {observation.data_quality.state.value.upper()}",
                ),
                mo.md("| Severity | Code | Evidence |\n| --- | --- | --- |\n" + _rows),
            ],
            gap=0.8,
        )
    return quality_view


@app.cell
def _(
    demo_prepare_error,
    demo_prepare_success,
    mo,
    prepare_demo_source_button,
):
    if demo_prepare_error:
        _status = mo.callout(
            demo_prepare_error,
            kind="danger",
            title="Bundled demo · Failed",
        )
    elif demo_prepare_success:
        _status = mo.callout(
            demo_prepare_success
            + ". Next: open Sources → select demo-bearing-snapshot → Analyze FILE snapshot.",
            kind="success",
            title="Bundled demo · Ready",
        )
    else:
        _status = mo.callout(
            "Registers and validates a small synthetic FILE snapshot shipped with the repository. "
            "It is only a workflow demo: the signal does not represent a real fault, degradation "
            "trajectory or RUL.",
            kind="info",
            title="No external dataset required",
        )

    bundled_demo_view = mo.vstack(
        [
            mo.md(
                "### Try the complete workflow\n\n"
                "1. Prepare the bundled demo source.\n"
                "2. **Sources** → Analyze FILE snapshot.\n"
                "3. **Investigation** → inspect AnalysisRun/evidence and create REVIEW_REQUIRED.\n"
                "4. **Maintenance Review** → note / acknowledge / close."
            ),
            prepare_demo_source_button,
            _status,
        ],
        gap=0.7,
    )
    return (bundled_demo_view,)


@app.cell
def _(
    bundled_demo_view,
    connection_status,
    mo,
    observation_detail,
    operational_findings,
    overview_stats,
    quality_view,
):
    _finding_status = (
        mo.callout(
            f"{len(operational_findings)} explicit REVIEW_REQUIRED finding(s) are stored. "
            "These are human review requests, not automated fault or health verdicts.",
            kind="warn",
            title="Findings · Review required",
        )
        if operational_findings
        else mo.callout(
            "No explicit REVIEW_REQUIRED finding is stored. "
            "Investigation can create one from a persisted AnalysisRun.",
            kind="neutral",
            title="Findings · None",
        )
    )
    overview_view = mo.vstack(
        [
            mo.md(
                "## Operations Overview\n\n"
                "현재 연결된 source, observation, analysis와 review workflow만 표시합니다."
            ),
            bundled_demo_view,
            overview_stats,
            connection_status,
            mo.hstack(
                [
                    _finding_status,
                    mo.callout(
                        "Finding review supports note, acknowledge and close. "
                        "It does not execute inspection, repair or a work order.",
                        kind="info",
                        title="Maintenance Review · Available",
                    ),
                ],
                widths="equal",
            ),
            mo.callout(
                "Automatic condition/fault/alert semantics and operational RUL are not "
                "implemented for field sources. Research anomaly/RUL evidence remains in "
                "Analysis Explorer and is not presented as an Operations capability.",
                kind="neutral",
                title="Unsupported operational semantics",
            ),
            observation_detail,
            quality_view,
        ],
        gap=1.2,
    )
    return overview_view


@app.cell
def _(mo, timeline):
    if timeline is None:
        observation_timeline_view = mo.callout(
            "Load a prepared history directory to review multiple timestamped "
            "observation segments.",
            kind="neutral",
            title="Observation timeline · Unavailable",
        )
    else:
        _rows = []
        for _index, _segment in enumerate(timeline.segments, start=1):
            if _segment.observed_start_at is None or _segment.observed_end_at is None:
                raise AssertionError(
                    "validated observation timeline segment timestamps unexpectedly missing"
                )
            _snapshot_name = (
                "Not recorded"
                if _segment.source_snapshot is None
                else _segment.source_snapshot.name
            )
            _rows.append(
                f"| {_index} | {_segment.observed_start_at.isoformat()} | "
                f"{_segment.observed_end_at.isoformat()} | {_segment.sample_count:,} | "
                f"{_segment.data_quality.state.value.upper()} | `{_snapshot_name}` |"
            )
        observation_timeline_view = mo.vstack(
            [
                mo.hstack(
                    [
                        mo.stat(
                            str(timeline.segment_count),
                            label="Observed segments",
                            caption="Ordered by recorded source timestamp",
                        ),
                        mo.stat(
                            timeline.observed_start_at.isoformat(),
                            label="History start",
                            caption="First recorded observation",
                        ),
                        mo.stat(
                            timeline.observed_end_at.isoformat(),
                            label="History end",
                            caption="Latest recorded observation",
                        ),
                    ],
                    widths="equal",
                ),
                mo.md(
                    "| # | Observed start | Observed end | Samples | Quality | Source snapshot |\n"
                    "| ---: | --- | --- | ---: | --- | --- |\n" + "\n".join(_rows)
                ),
                mo.callout(
                    "This is an observation timeline only. Ordering source segments by "
                    "recorded time does not create an anomaly, condition, health or RUL trend.",
                    kind="info",
                    title="Timeline semantics",
                ),
            ],
            gap=0.8,
        )
    return observation_timeline_view


@app.cell
def _(
    create_review_finding_button,
    field_analysis_error,
    field_analysis_result,
    field_analysis_results,
    field_analysis_state_path,
    finding_action_error,
    finding_state_path,
    mo,
    observation_timeline_view,
    operational_findings,
):
    if field_analysis_error:
        _field_analysis_view = mo.callout(
            field_analysis_error,
            kind="danger",
            title="Operational AnalysisRun · Failed",
        )
    elif field_analysis_result is None:
        _field_analysis_view = mo.callout(
            "No persisted operational field feature analysis is available. "
            "Select a supported registered FILE snapshot in Sources and run Analyze FILE snapshot.",
            kind="neutral",
            title="Analysis Run · Not run",
        )
    else:
        _run = field_analysis_result.run
        _evidence = field_analysis_result.evidence
        _feature_rows = "\n".join(
            f"| `{name}` | {value:.6g} |"
            for name, value in zip(_evidence.feature_names, _evidence.values, strict=True)
        )
        _field_analysis_view = mo.vstack(
            [
                mo.md(
                    "### Operational AnalysisRun\n\n"
                    "| Field | Value |\n"
                    "| --- | --- |\n"
                    f"| Run | `{_run.analysis_run_id}` |\n"
                    f"| Source | `{_run.source_id}` |\n"
                    f"| Asset | `{_run.asset_id}` |\n"
                    f"| Measurement point | "
                    f"`{_run.measurement_point_id or 'Not recorded'}` |\n"
                    f"| Observed | {_run.observed_start_at.isoformat()} → "
                    f"{_run.observed_end_at.isoformat()} |\n"
                    f"| Executed | {_run.started_at.isoformat()} → "
                    f"{_run.completed_at.isoformat()} |\n"
                    f"| Data quality | {_run.data_quality.state.value.upper()} |\n"
                    f"| Capability | `{_evidence.capability_id}` |\n"
                    f"| Feature set | `{_evidence.feature_set_id}` |\n"
                    f"| Evidence | `{_evidence.evidence_id}` |"
                ),
                mo.md(
                    "### Vibration feature evidence\n\n"
                    "| Feature | Value |\n"
                    "| --- | ---: |\n" + _feature_rows
                ),
                mo.callout(
                    "These are waveform statistics from one exact FILE snapshot. "
                    "They are operational analysis evidence, but no threshold/state policy "
                    "has interpreted them as anomaly, fault, health, alert or maintenance need.",
                    kind="info",
                    title="Feature evidence semantics",
                ),
            ],
            gap=0.8,
        )

    if not field_analysis_results:
        _field_analysis_history_view = mo.callout(
            f"No saved operational AnalysisRun exists at `{field_analysis_state_path}`.",
            kind="neutral",
            title="Operational analysis history · Empty",
        )
    else:
        _history_rows = "\n".join(
            f"| {result.run.completed_at.isoformat()} | "
            f"`{result.run.analysis_run_id}` | `{result.run.source_id}` | "
            f"`{result.run.asset_id}` | "
            f"{result.run.data_quality.state.value.upper()} | "
            f"`{result.evidence.feature_set_id}` |"
            for result in reversed(field_analysis_results[-20:])
        )
        _field_analysis_history_view = mo.vstack(
            [
                mo.md(
                    "### Operational analysis history\n\n"
                    "| Completed | Run | Source | Asset | Quality | Feature set |\n"
                    "| --- | --- | --- | --- | --- | --- |\n" + _history_rows
                ),
                mo.callout(
                    f"Persisted history: `{field_analysis_state_path}`. "
                    "Each row is an AnalysisRun plus feature evidence, not a finding.",
                    kind="info",
                    title=f"Saved AnalysisRun · {len(field_analysis_results)} total",
                ),
            ],
            gap=0.8,
        )

    if finding_action_error:
        _finding_view = mo.callout(
            finding_action_error,
            kind="danger",
            title="Review finding · Failed",
        )
    elif field_analysis_result is None:
        _finding_view = mo.callout(
            "Run a supported operational FILE analysis before creating a review finding.",
            kind="neutral",
            title="Finding · No AnalysisRun",
        )
    else:
        _current_findings = tuple(
            finding
            for finding in operational_findings
            if finding.analysis_run_id == field_analysis_result.run.analysis_run_id
        )
        if _current_findings:
            _finding = _current_findings[-1]
            _evidence_refs = ", ".join("`" + ref + "`" for ref in _finding.evidence_refs)
            _finding_view = mo.vstack(
                [
                    mo.md(
                        "### Review finding\n\n"
                        "| Field | Value |\n"
                        "| --- | --- |\n"
                        f"| Finding | `{_finding.finding_id}` |\n"
                        f"| State | **{_finding.state}** |\n"
                        f"| Semantics | `{_finding.finding_semantics_id}` |\n"
                        f"| Analysis run | `{_finding.analysis_run_id}` |\n"
                        f"| Evidence | {_evidence_refs} |"
                    ),
                    mo.callout(
                        f"Persisted at `{finding_state_path}`. This finding exists because "
                        "a user explicitly requested review of the feature evidence. "
                        "It is not an automated anomaly, fault, health or alarm verdict.",
                        kind="warn",
                        title="Human review request",
                    ),
                ],
                gap=0.8,
            )
        else:
            _finding_view = mo.vstack(
                [
                    create_review_finding_button,
                    mo.callout(
                        "Creates a durable OperationalFinding with state REVIEW_REQUIRED and "
                        "human-review-request-v1 semantics, linked to the current feature "
                        "evidence. Pressing this button records a workflow request; it does not "
                        "interpret the feature values as abnormal.",
                        kind="info",
                        title="Manual finding creation",
                    ),
                ],
                gap=0.6,
            )

    if operational_findings:
        _finding_rows = "\n".join(
            f"| {_finding.observed_at.isoformat()} | `{_finding.finding_id}` | "
            f"`{_finding.asset_id}` | {_finding.state} | "
            f"`{_finding.finding_semantics_id}` |"
            for _finding in reversed(operational_findings[-20:])
        )
        _finding_history_view = mo.md(
            "### Finding history\n\n"
            "| Observed at | Finding | Asset | State | Semantics |\n"
            "| --- | --- | --- | --- | --- |\n" + _finding_rows
        )
    else:
        _finding_history_view = mo.callout(
            f"No finding is stored at `{finding_state_path}`.",
            kind="neutral",
            title="Finding history · Empty",
        )

    investigation_view = mo.vstack(
        [
            mo.md(
                "## Investigation\n\n"
                "관측 사실과 PHM evidence를 같은 흐름에서 검토하기 위한 운영 surface입니다."
            ),
            _field_analysis_view,
            _field_analysis_history_view,
            _finding_view,
            _finding_history_view,
            observation_timeline_view,
            mo.callout(
                "The current FILE analysis produces vibration feature evidence and can create "
                "an explicit human review request. It does not produce validated condition, "
                "fault, alert or operational RUL semantics, and it does not execute maintenance.",
                kind="info",
                title="Current analysis boundary",
            ),
        ],
        gap=1.2,
    )
    return investigation_view


@app.cell
def _(mo, observation, quality_view):
    if observation is None:
        _source_mapping = mo.callout(
            "Load a prepared source to inspect its operational mapping and provenance.",
            kind="neutral",
            title="Source mapping · Unavailable",
        )
        _snapshot_evidence = mo.callout(
            "No exact source snapshot identity is available.",
            kind="neutral",
            title="Source snapshot · Unavailable",
        )
        _validation_policy = mo.callout(
            "No source-validation policy is available.",
            kind="neutral",
            title="Validation policy · Unavailable",
        )
    else:
        _source_mapping = mo.md(
            "### Source mapping\n\n"
            "| Field | Value |\n"
            "| --- | --- |\n"
            f"| Asset | `{observation.asset_id}` |\n"
            f"| Source | `{observation.source_id}` |\n"
            f"| Measurement point | "
            f"`{observation.measurement_point_id or 'Not recorded'}` |\n"
            f"| Channels | {', '.join(observation.channels)} |"
        )

        if observation.source_snapshot is None:
            _snapshot_evidence = mo.callout(
                "This observation does not provide exact byte-level source identity.",
                kind="neutral",
                title="Source snapshot · Not recorded",
            )
        else:
            _snapshot_evidence = mo.md(
                "### Source snapshot\n\n"
                "| Field | Recorded value |\n"
                "| --- | --- |\n"
                f"| File | `{observation.source_snapshot.name}` |\n"
                f"| SHA-256 | `{observation.source_snapshot.sha256}` |\n"
                f"| Size | {observation.source_snapshot.size_bytes:,} bytes |"
            )

        if observation.validation_policy is None:
            _validation_policy = mo.callout(
                "This observation does not provide declared validation-policy evidence.",
                kind="neutral",
                title="Validation policy · Not recorded",
            )
        else:
            _timestamp_field = (
                observation.validation_policy.source_timestamp_field or "Not declared"
            )
            _tolerance = observation.validation_policy.sampling_rate_tolerance_ratio
            _tolerance_label = "Not declared" if _tolerance is None else f"{_tolerance:g}"
            _validation_policy = mo.md(
                "### Validation policy\n\n"
                "| Policy | Declared value |\n"
                "| --- | --- |\n"
                f"| Source timestamp field | `{_timestamp_field}` |\n"
                f"| Minimum samples | "
                f"{observation.validation_policy.minimum_sample_count:,} |\n"
                f"| Sampling-rate tolerance ratio | {_tolerance_label} |"
            )

    data_quality_view = mo.vstack(
        [
            mo.md(
                "## Data Quality & Evidence\n\n"
                "운영 판단 전에 source identity, validation policy와 품질 evidence를 "
                "독립적으로 확인합니다."
            ),
            quality_view,
            _source_mapping,
            _snapshot_evidence,
            _validation_policy,
            mo.callout(
                "The current baseline does not auto-repair, resample, interpolate or "
                "drop blocking source values to manufacture a PASS.",
                kind="info",
                title="Validation behavior",
            ),
            mo.callout(
                "Vendor quality flags, sensor calibration/replacement state and operating "
                "context are not first-class evidence yet. Their absence is visible here "
                "instead of being folded into a generic quality score.",
                kind="neutral",
                title="Additional quality semantics · Not recorded",
            ),
        ],
        gap=1.2,
    )
    return data_quality_view


@app.cell
def _(
    FindingReviewStatus,
    finding_review_error,
    finding_review_events,
    finding_review_state_path,
    finding_review_status,
    maintenance_acknowledge_button,
    maintenance_add_note_button,
    maintenance_close_button,
    maintenance_finding_selector,
    maintenance_note_input,
    mo,
    operational_findings,
):
    if finding_review_error:
        maintenance_view = mo.vstack(
            [
                mo.md("## Maintenance Review"),
                mo.callout(
                    finding_review_error,
                    kind="danger",
                    title="Finding review state · Unavailable",
                ),
            ],
            gap=1.0,
        )
    elif not operational_findings:
        maintenance_view = mo.vstack(
            [
                mo.md("## Maintenance Review"),
                mo.callout(
                    "Create a REVIEW_REQUIRED finding in Investigation first. "
                    "Maintenance review starts from an existing OperationalFinding.",
                    kind="neutral",
                    title="No finding to review",
                ),
                mo.callout(
                    "This workflow does not create a work order or claim that maintenance "
                    "is required.",
                    kind="info",
                    title="Current scope",
                ),
            ],
            gap=1.0,
        )
    else:
        assert maintenance_finding_selector is not None
        _finding = next(
            finding
            for finding in operational_findings
            if finding.finding_id == maintenance_finding_selector.value
        )
        _events = tuple(
            event for event in finding_review_events if event.finding_id == _finding.finding_id
        )
        try:
            _status = finding_review_status(_events, _finding.finding_id)
            _status_error = ""
        except ValueError as error:
            _status = FindingReviewStatus.OPEN
            _status_error = str(error)

        _event_rows = "\n".join(
            f"| {event.recorded_at.isoformat()} | {event.action.value} | "
            f"{event.note.replace('|', '&#124;') or '-'} |"
            for event in _events
        )
        _history = (
            mo.md(
                "### Review history\n\n"
                "| Recorded at | Action | Note |\n"
                "| --- | --- | --- |\n" + _event_rows
            )
            if _events
            else mo.callout(
                "No review action has been recorded for this finding.",
                kind="neutral",
                title="Review history · Empty",
            )
        )

        _controls = []
        if _status_error:
            _controls.append(
                mo.callout(
                    _status_error,
                    kind="danger",
                    title="Review transition state invalid",
                )
            )
        elif _status == FindingReviewStatus.OPEN:
            assert maintenance_note_input is not None
            assert maintenance_add_note_button is not None
            assert maintenance_acknowledge_button is not None
            _controls.extend(
                [
                    maintenance_note_input,
                    mo.hstack(
                        [maintenance_add_note_button, maintenance_acknowledge_button],
                        widths="equal",
                    ),
                ]
            )
        elif _status == FindingReviewStatus.ACKNOWLEDGED:
            assert maintenance_note_input is not None
            assert maintenance_add_note_button is not None
            assert maintenance_close_button is not None
            _controls.extend(
                [
                    maintenance_note_input,
                    mo.hstack(
                        [maintenance_add_note_button, maintenance_close_button],
                        widths="equal",
                    ),
                ]
            )
        else:
            _controls.append(
                mo.callout(
                    "This review workflow is closed. Closed means the human review is "
                    "finished; it does not mean the asset is repaired, healthy, or returned "
                    "to service.",
                    kind="success",
                    title="Review workflow closed",
                )
            )

        maintenance_view = mo.vstack(
            [
                mo.md(
                    "## Maintenance Review\n\n"
                    "Operational finding에 대한 사람의 검토 책임과 종료를 기록합니다."
                ),
                maintenance_finding_selector,
                mo.hstack(
                    [
                        mo.stat(
                            _status.value.upper(),
                            label="Review status",
                            caption="Human workflow state",
                        ),
                        mo.stat(
                            str(len(_events)),
                            label="Review events",
                            caption="Append-only actions",
                        ),
                    ],
                    widths="equal",
                ),
                mo.md(
                    "### Finding\n\n"
                    "| Field | Value |\n"
                    "| --- | --- |\n"
                    f"| Finding | `{_finding.finding_id}` |\n"
                    f"| Finding state | **{_finding.state}** |\n"
                    f"| Semantics | `{_finding.finding_semantics_id}` |\n"
                    f"| Asset | `{_finding.asset_id}` |\n"
                    f"| Observed at | {_finding.observed_at.isoformat()} |"
                ),
                *_controls,
                _history,
                mo.callout(
                    f"Review state: `{finding_review_state_path}`. "
                    "Acknowledge means a person accepted review responsibility. Close means "
                    "the review workflow ended. Neither action confirms a fault, repair, "
                    "maintenance execution, or asset health. No work order/CMMS action is sent.",
                    kind="info",
                    title="Maintenance review semantics",
                ),
            ],
            gap=1.0,
        )
    return (maintenance_view,)


@app.cell
def _(
    FindingReviewStatus,
    SourceLifecycleState,
    field_analysis_error,
    field_analysis_results,
    field_analysis_state_error,
    field_analysis_state_path,
    finding_action_error,
    finding_review_error,
    finding_review_events,
    finding_review_state_error,
    finding_review_state_path,
    finding_review_status,
    finding_state_error,
    finding_state_path,
    mo,
    operational_findings,
    registered_sources,
    source_lifecycle_records,
    source_registry_default,
    source_registry_error,
    source_runtime_connection_attempts,
    source_runtime_default,
    source_runtime_error,
    source_runtime_receipts,
):
    _lifecycle_by_id = {record.source_id: record for record in source_lifecycle_records}
    _active_source_count = sum(
        1
        for source in registered_sources
        if (
            (record := _lifecycle_by_id.get(source.source_id)) is not None
            and record.state == SourceLifecycleState.ACTIVE
        )
    )
    _latest_analysis_at = (
        None
        if not field_analysis_results
        else max(result.run.completed_at for result in field_analysis_results)
    )

    _review_statuses = []
    _review_status_error = ""
    try:
        _review_statuses = [
            finding_review_status(finding_review_events, finding.finding_id)
            for finding in operational_findings
        ]
    except ValueError as error:
        _review_status_error = str(error)

    _open_review_count = sum(status == FindingReviewStatus.OPEN for status in _review_statuses)
    _acknowledged_review_count = sum(
        status == FindingReviewStatus.ACKNOWLEDGED for status in _review_statuses
    )
    _closed_review_count = sum(status == FindingReviewStatus.CLOSED for status in _review_statuses)

    _store_rows = [
        (
            "Source registry",
            source_registry_default,
            source_registry_error,
            f"{len(registered_sources)} source(s)",
        ),
        (
            "Source runtime",
            source_runtime_default,
            source_runtime_error,
            (
                f"{len(source_runtime_receipts)} receipt(s), "
                f"{len(source_runtime_connection_attempts)} attempt(s)"
            ),
        ),
        (
            "Operational analysis",
            str(field_analysis_state_path),
            field_analysis_state_error,
            f"{len(field_analysis_results)} run(s)",
        ),
        (
            "Operational findings",
            str(finding_state_path),
            finding_state_error,
            f"{len(operational_findings)} finding(s)",
        ),
        (
            "Maintenance review",
            str(finding_review_state_path),
            finding_review_state_error,
            f"{len(finding_review_events)} event(s)",
        ),
    ]
    _store_table = "\n".join(
        "| {name} | {status} | `{path}` | {detail} |".format(
            name=name,
            status="ERROR" if error else "AVAILABLE",
            path=path.replace("|", "&#124;"),
            detail=detail,
        )
        for name, path, error, detail in _store_rows
    )

    _current_errors = tuple(
        (label, error)
        for label, error in (
            ("Source registry/runtime", source_registry_error or source_runtime_error),
            ("Analysis", field_analysis_error),
            ("Finding", finding_action_error),
            ("Maintenance review", finding_review_error or _review_status_error),
        )
        if error
    )
    if _current_errors:
        _error_rows = "\n".join(f"- **{label}**: {error}" for label, error in _current_errors)
        _current_error_view = mo.callout(
            _error_rows,
            kind="danger",
            title=f"Current operational errors · {len(_current_errors)}",
        )
    else:
        _current_error_view = mo.callout(
            "No current application/store error is recorded by this Operations process.",
            kind="success",
            title="Current operational errors · None",
        )

    operational_state_view = mo.vstack(
        [
            mo.md(
                "## Operational State\n\n"
                "현재 Operations process가 실제로 읽을 수 있는 local control/runtime/application "
                "state와 recorded population을 확인합니다."
            ),
            mo.hstack(
                [
                    mo.stat(
                        f"{len(registered_sources)} / {_active_source_count}",
                        label="Sources / active",
                        caption="Registered control-plane state",
                    ),
                    mo.stat(
                        str(len(field_analysis_results)),
                        label="Analysis runs",
                        caption=(
                            "No saved run"
                            if _latest_analysis_at is None
                            else f"Latest {_latest_analysis_at.isoformat()}"
                        ),
                    ),
                    mo.stat(
                        str(len(operational_findings)),
                        label="Findings",
                        caption="Explicit human-review-request findings",
                    ),
                    mo.stat(
                        (
                            f"{_open_review_count} / "
                            f"{_acknowledged_review_count} / {_closed_review_count}"
                        ),
                        label="Review O / A / C",
                        caption="Open / acknowledged / closed",
                    ),
                ],
                widths="equal",
            ),
            mo.md(
                "### Local operational state\n\n"
                "| Store | Status | Path | Recorded population |\n"
                "| --- | --- | --- | --- |\n" + _store_table
            ),
            _current_error_view,
            mo.callout(
                "AVAILABLE means the local state repository was readable by this app; it is "
                "not a service-availability SLA. Source connection is still not continuously "
                "instrumented, and there is no queue/backlog/latency/process metric pipeline. "
                "This screen does not infer asset health from platform state.",
                kind="info",
                title="Operational-state semantics",
            ),
        ],
        gap=1.2,
    )
    return operational_state_view


@app.cell
def _(
    asset_input,
    channels_input,
    history_directory_input,
    load_button,
    measurement_point_input,
    mo,
    sampling_rate_input,
    source_id_input,
    source_input,
    timestamp_input,
):
    source_setup = mo.accordion(
        {
            "Prepared source inspection": mo.vstack(
                [
                    mo.md(
                        "로컬 prepared CSV snapshot/history를 일회성으로 확인하는 입력입니다. "
                        "지속적으로 관리할 source는 Sources에서 등록·실행합니다. "
                        "History directory가 입력되면 single CSV보다 우선하며, "
                        "이 inspection 입력은 "
                        "historian/API나 continuous ingestion을 의미하지 않습니다."
                    ),
                    source_input,
                    history_directory_input,
                    mo.hstack([asset_input, source_id_input], widths="equal"),
                    mo.hstack(
                        [measurement_point_input, channels_input],
                        widths="equal",
                    ),
                    mo.hstack(
                        [timestamp_input, sampling_rate_input],
                        widths="equal",
                    ),
                    load_button,
                ],
                gap=0.8,
            )
        }
    )
    return source_setup


@app.cell
def _(
    data_quality_view,
    investigation_view,
    maintenance_view,
    mo,
    overview_view,
    page_selector,
    source_setup,
    sources_view,
    operational_state_view,
):
    views = {
        "Overview": overview_view,
        "Sources": sources_view,
        "Investigation": investigation_view,
        "Data Quality": data_quality_view,
        "Maintenance Review": maintenance_view,
        "Operational State": operational_state_view,
    }
    _header_items = [
        mo.md(
            "# PHM Operations\n\n"
            "현재 **Source → Analyze → Results → Finding → Maintenance Review**의 "
            "FILE snapshot workflow가 연결되어 있습니다."
        ),
        mo.callout(
            "Primary navigation에는 현재 실행하거나 검토할 수 있는 Operations 기능만 둡니다. "
            "Automatic condition/fault/alert semantics, operational RUL, work-order/CMMS "
            "execution은 현재 Operations capability가 아닙니다.",
            kind="info",
            title="Current product milestone",
        ),
        page_selector,
    ]
    if page_selector.value == "Overview":
        _header_items.append(source_setup)
    header = mo.vstack(_header_items, gap=1.0)
    mo.vstack([header, views[page_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
