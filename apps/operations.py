import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from datetime import datetime
    from pathlib import Path

    import marimo as mo

    from industrial_phm.adapters import CsvSensorLayout, CsvSensorSourceError
    from industrial_phm.application import (
        AssetObservationSummary,
        AssetObservationTimeline,
        FileSourceConfig,
        FileSourceMode,
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        OpcUaSourceConfig,
        RegisteredSource,
        SourceFreshnessPolicy,
        SourceLifecycleState,
        SourceRuntimeCycleState,
        assess_source_freshness,
        assess_source_health,
        discover_file_source,
        load_field_csv_observation_summary,
        load_field_csv_observation_timeline_directory,
        receive_registered_file_source_observation,
        register_file_source,
        run_registered_file_source_cycle,
        transition_source_lifecycle,
        validate_distinct_source_state_paths,
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
        JsonSourceRepository,
        JsonSourceRuntimeRepository,
        OpcUaSourceConfig,
        Path,
        RegisteredSource,
        SourceFreshnessPolicy,
        SourceLifecycleState,
        SourceRuntimeCycleState,
        assess_source_freshness,
        assess_source_health,
        datetime,
        discover_file_source,
        load_field_csv_observation_summary,
        load_field_csv_observation_timeline_directory,
        receive_registered_file_source_observation,
        mo,
        register_file_source,
        run_registered_file_source_cycle,
        transition_source_lifecycle,
        validate_distinct_source_state_paths,
        os,
    )


@app.cell
def _(
    CsvSensorLayout,
    CsvSensorSourceError,
    Path,
    load_field_csv_observation_summary,
    load_field_csv_observation_timeline_directory,
):
    def parse_channels(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def parse_sampling_rate(value: str) -> float | None:
        return None if not value.strip() else float(value)

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

    return load_observation, parse_channels, parse_sampling_rate


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
        initial_source_runtime_error = ""
    except (OSError, ValueError) as error:
        initial_source_runtime_receipts = ()
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
    get_source_runtime_receipts, set_source_runtime_receipts = mo.state(
        initial_source_runtime_receipts
    )
    return (
        get_registered_sources,
        get_source_freshness_policies,
        get_source_lifecycle_records,
        get_source_registry_error,
        get_source_runtime_error,
        get_source_runtime_receipts,
        set_registered_sources,
        set_source_freshness_policies,
        set_source_lifecycle_records,
        set_source_registry_error,
        set_source_runtime_error,
        set_source_runtime_receipts,
    )


@app.cell
def _(
    get_registered_sources,
    get_source_freshness_policies,
    get_source_lifecycle_records,
    get_source_registry_error,
    get_source_runtime_error,
    get_source_runtime_receipts,
):
    registered_sources = get_registered_sources()
    source_freshness_policies = get_source_freshness_policies()
    source_lifecycle_records = get_source_lifecycle_records()
    source_registry_error = get_source_registry_error()
    source_runtime_error = get_source_runtime_error()
    source_runtime_receipts = get_source_runtime_receipts()
    return (
        registered_sources,
        source_freshness_policies,
        source_lifecycle_records,
        source_registry_error,
        source_runtime_error,
        source_runtime_receipts,
    )


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
            "Assets",
            "Asset",
            "Investigation",
            "Data Quality",
            "Maintenance",
            "System Health",
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
    return (
        asset_input,
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
def _(FileSourceMode, mo):
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
    return (
        discover_source_button,
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
    )


@app.cell
def _(mo):
    get_source_discovery, set_source_discovery = mo.state(None)
    get_discovery_signature, set_discovery_signature = mo.state(None)
    get_registration_validation, set_registration_validation = mo.state(None)
    get_registration_error, set_registration_error = mo.state("")
    get_registration_success, set_registration_success = mo.state("")
    return (
        get_discovery_signature,
        get_registration_error,
        get_registration_success,
        get_registration_validation,
        get_source_discovery,
        set_discovery_signature,
        set_registration_error,
        set_registration_success,
        set_registration_validation,
        set_source_discovery,
    )


@app.cell
def _(
    FileSourceMode,
    Path,
    discover_file_source,
    discover_source_button,
    registration_delimiter_input,
    registration_mode_input,
    registration_path_input,
    set_discovery_signature,
    set_registration_error,
    set_registration_success,
    set_registration_validation,
    set_source_discovery,
):
    if discover_source_button.value:
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
    get_registration_error,
    get_registration_success,
    get_registration_validation,
    get_source_discovery,
):
    discovery_signature = get_discovery_signature()
    registration_error = get_registration_error()
    registration_success = get_registration_success()
    registration_validation = get_registration_validation()
    source_discovery = get_source_discovery()
    return (
        discovery_signature,
        registration_error,
        registration_success,
        registration_validation,
        source_discovery,
    )


@app.cell
def _(
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    Path,
    RegisteredSource,
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
    if register_source_button.value:
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
    discovery_signature,
    registration_asset_id_input,
    registration_channels_input,
    registration_delimiter_input,
    registration_error,
    registration_measurement_point_input,
    registration_minimum_samples_input,
    registration_mode_input,
    registration_name_input,
    registration_path_input,
    registration_sampling_rate_input,
    registration_source_id_input,
    registration_success,
    registration_timestamp_input,
    registration_tolerance_input,
    registration_validation,
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

    if registration_error:
        _registration_status = mo.callout(
            registration_error,
            kind="danger",
            title="Validate & Register · Failed",
        )
    elif registration_validation is not None and registration_success:
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
    else:
        _registration_status = mo.callout(
            "Registration validates the entire declared snapshot/history before persisting it.",
            kind="info",
            title="Validate & Register",
        )

    registration_view = mo.vstack(
        [
            mo.md(
                "### Add source\n\n"
                "**1. Source** — 현재는 prepared CSV file/history directory만 등록합니다. "
                "OPC UA/MQTT는 아직 선택 가능한 capability가 아닙니다."
            ),
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
        load_registered_source_button = mo.ui.run_button(
            label="Load registered source",
        )
    else:
        source_selector = None
        activate_source_button = None
        pause_source_button = None
        freshness_age_input = None
        save_freshness_policy_button = None
        clear_freshness_policy_button = None
        run_active_source_button = None
        load_registered_source_button = None
    return (
        activate_source_button,
        clear_freshness_policy_button,
        freshness_age_input,
        load_registered_source_button,
        pause_source_button,
        run_active_source_button,
        save_freshness_policy_button,
        source_selector,
    )


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
    assess_source_freshness,
    assess_source_health,
    clear_freshness_policy_button,
    datetime,
    freshness_age_input,
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
    source_freshness_policies,
    source_lifecycle_records,
    source_registry_default,
    source_receipt,
    source_registry_error,
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
                    "Use Add source above to discover, map, validate and register a prepared "
                    "CSV file or timestamped history directory.",
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
                        "verdict. Registration and persistence alone do not provide live "
                        "connector telemetry, so connection remains NOT_INSTRUMENTED until a "
                        "source runtime records that evidence.",
                        kind="info",
                        title="Health semantics",
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
                        "received_at is the time this prepared source load was accepted after "
                        "validation. It is not reconstructed sensor transport arrival time.",
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
                            "Type-specific",
                            label="Ingestion",
                            caption="FILE one-shot; OPC UA runtime not connected yet",
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
                (
                    run_active_source_button
                    if _selected_is_file
                    else mo.callout(
                        "OPC UA registration is persisted, but an operational connector runtime "
                        "is not connected yet. One-shot connector proof, subscription and "
                        "connection telemetry remain separate boundaries.",
                        kind="neutral",
                        title="OPC UA runtime · Unavailable",
                    )
                ),
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
                                "Run active source once consumes only ACTIVE lifecycle state. "
                                "It re-validates the registered file/history source, records the "
                                "latest receipt and leaves lifecycle ACTIVE on success. Source "
                                "validation/I/O failure transitions ACTIVE → ERROR, while platform "
                                "runtime-state failure fails the cycle without changing source "
                                "lifecycle. This is one explicit iteration, not background "
                                "polling.",
                                kind="info",
                                title="Runtime cycle semantics",
                            )
                        )
                    )
                    if _selected_is_file
                    else mo.callout(
                        "No runtime-cycle result is produced for OPC UA registration yet.",
                        kind="neutral",
                        title="Runtime evidence · Unavailable",
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
                mo.md("### Load current observation"),
                (
                    load_registered_source_button
                    if _selected_is_file
                    else mo.callout(
                        "Registered OPC UA source has no observation loader yet. Live connector "
                        "receipt/observation projection is a later runtime slice.",
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
                        "No on-demand observation result is produced for OPC UA registration.",
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
                        "Latest accepted registered-source receipt is persisted separately "
                        "from the source registry. Only latest receipt timing is stored; "
                        "connection status, retry/buffer state and receipt history are not.",
                        kind="info",
                        title="Runtime receipt persistence",
                    )
                ),
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
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    Path,
    SourceRuntimeCycleState,
    run_active_source_button,
    run_registered_file_source_cycle,
    set_load_error,
    set_observation,
    set_runtime_cycle_error,
    set_runtime_cycle_skipped,
    set_runtime_cycle_success,
    set_source_lifecycle_records,
    set_source_receipt,
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
            _result = run_registered_file_source_cycle(
                _source_repository,
                _source_repository,
                _runtime_repository,
                source_selector.value,
            )
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
                    set_observation(_loaded.latest)
                    set_timeline(_loaded.timeline)
                    set_source_receipt(_received.receipt)
                    set_load_error("")
                    set_runtime_cycle_error("")
                    set_runtime_cycle_skipped("")
                    set_runtime_cycle_success(
                        f"Runtime cycle succeeded: {_result.source_id} · "
                        f"received {_received.receipt.received_at.isoformat()}"
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
            except (OSError, ValueError) as error:
                set_source_runtime_error(str(error))
            else:
                set_source_runtime_receipts(_runtime_receipts)
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
def _(DataQualityState, mo, observation):
    if observation is None:
        asset_label = "Not connected"
        last_observed_label = "Unavailable"
        quality_label = "Unavailable"
        quality_caption = "Load a prepared field source"
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
                "Unavailable",
                label="PHM finding",
                caption="No validated field finding contract yet",
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
            "No field source is connected. The Operations structure remains visible so "
            "missing capabilities are explicit rather than hidden.",
            kind="neutral",
            title="Observation source not connected",
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
            "Prepared field observation loaded through the application boundary. "
            "This confirms source structure and recorded quality only; it does not "
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
            "here after a prepared source is loaded.",
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
            "The prepared source passed the currently declared structural and sampling "
            "checks with no recorded warnings.",
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
def _(connection_status, mo, observation_detail, overview_stats, quality_view):
    overview_view = mo.vstack(
        [
            mo.md(
                "## Operations Overview\n\n"
                "관측·품질·PHM·정비 capability를 같은 운영 구조에서 확인합니다."
            ),
            overview_stats,
            connection_status,
            mo.hstack(
                [
                    mo.callout(
                        "No validated field condition/health state is available yet. "
                        "A score will not be promoted to a health state without a "
                        "field-specific validation policy.",
                        kind="neutral",
                        title="Condition · Not validated",
                    ),
                    mo.callout(
                        "No operational finding has been issued. This does not mean "
                        "the asset is normal; the field finding pipeline is not connected yet.",
                        kind="neutral",
                        title="Findings · Unavailable",
                    ),
                    mo.callout(
                        "No validated alert policy exists for the current field source. "
                        "Anomaly scores are not promoted to alerts without that policy.",
                        kind="neutral",
                        title="Alerts · Not validated",
                    ),
                ],
                widths="equal",
            ),
            mo.hstack(
                [
                    mo.callout(
                        "No field prognostics estimate is connected. Development RUL "
                        "evidence from research artifacts is not reused as an operational RUL.",
                        kind="neutral",
                        title="RUL · Unavailable",
                    ),
                    mo.callout(
                        "Maintenance history and work-order context are not connected yet.",
                        kind="neutral",
                        title="Maintenance · Not connected",
                    ),
                ],
                widths="equal",
            ),
            observation_detail,
            quality_view,
        ],
        gap=1.2,
    )
    return overview_view


@app.cell
def _(mo, observation, observation_detail, observation_timeline_view, quality_view):
    if observation is None:
        _identity = mo.callout(
            "Connect a prepared field source to inspect the asset and measurement point.",
            kind="neutral",
            title="Asset identity unavailable",
        )
    else:
        _identity = mo.callout(
            f"Viewing `{observation.asset_id}`"
            + (
                ""
                if observation.measurement_point_id is None
                else f" / `{observation.measurement_point_id}`"
            ),
            kind="info",
            title="Asset context",
        )

    asset_view = mo.vstack(
        [
            mo.md("## Asset"),
            _identity,
            observation_detail,
            observation_timeline_view,
            quality_view,
            mo.callout(
                "Freshness policy is not configured. The UI shows the recorded source "
                "timestamp but does not label data fresh/stale until a product policy exists.",
                kind="neutral",
                title="Freshness · Not configured",
            ),
            mo.callout(
                "Sensor identity, unit, observed property and calibration history are not "
                "yet first-class operational contracts. Their slots are reserved here and "
                "will be populated from the first private source that requires them.",
                kind="neutral",
                title="Sensor context · Not recorded",
            ),
        ],
        gap=1.2,
    )
    return asset_view


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
def _(mo, observation_timeline_view):
    investigation_view = mo.vstack(
        [
            mo.md(
                "## Investigation\n\n"
                "관측 사실과 PHM evidence를 같은 흐름에서 검토하기 위한 운영 surface입니다."
            ),
            mo.callout(
                "The AnalysisRun contract now defines run ID, asset/measurement point, "
                "observation window, execution time, data quality, source snapshot "
                "provenance, model deployment and produced capability IDs. No field "
                "analysis producer is connected yet, so no run instance is shown.",
                kind="neutral",
                title="Analysis Run · Not connected",
            ),
            mo.callout(
                "OperationalFinding is available as an evidence-linked contract, but no "
                "validated field finding pipeline has produced one yet. A finding must "
                "reference a versioned finding semantics ID and supporting evidence.",
                kind="neutral",
                title="Finding · Unavailable",
            ),
            observation_timeline_view,
            mo.callout(
                "Anomaly/condition trend will appear only after a field analysis run "
                "produces capability-specific evidence with validated operational semantics.",
                kind="neutral",
                title="PHM Trend & Evidence · Unavailable",
            ),
            mo.callout(
                "No operational RUL estimate is available. Research benchmark RUL is "
                "kept in the PHM Workbench and is not copied into this surface.",
                kind="neutral",
                title="Prognostics · Unavailable",
            ),
            mo.callout(
                "No maintenance case, inspection note or work-order history is connected.",
                kind="neutral",
                title="Maintenance context · Not connected",
            ),
        ],
        gap=1.2,
    )
    return investigation_view


@app.cell
def _(mo, observation):
    if observation is None:
        assets_view = mo.vstack(
            [
                mo.md(
                    "## Assets\n\n"
                    "Fleet/asset inventory의 운영 자리입니다. 현재 bootstrap은 "
                    "single-asset source이지만 목록 surface는 처음부터 유지합니다."
                ),
                mo.callout(
                    "No observed asset is connected yet.",
                    kind="neutral",
                    title="Asset inventory · Empty",
                ),
            ],
            gap=1.2,
        )
    else:
        _last_observed = (
            "Unavailable"
            if observation.observed_end_at is None
            else observation.observed_end_at.isoformat()
        )
        _row = (
            f"| `{observation.asset_id}` | "
            f"`{observation.measurement_point_id or 'Not recorded'}` | "
            f"{_last_observed} | "
            f"{observation.data_quality.state.value.upper()} | "
            "Unavailable |"
        )
        assets_view = mo.vstack(
            [
                mo.md(
                    "## Assets\n\n"
                    "현재 연결된 observation population을 asset inventory 형태로 표시합니다. "
                    "향후 multi-asset repository/API가 연결되면 같은 surface가 "
                    "fleet list를 소비합니다."
                ),
                mo.md(
                    "| Asset | Measurement point | Last observed | Data quality | Finding |\n"
                    "| --- | --- | --- | --- | --- |\n" + _row
                ),
                mo.callout(
                    "The current field bootstrap exposes one asset identity at a time, "
                    "optionally across multiple timestamped segments. A one-row inventory "
                    "is a source limitation, not the final fleet model.",
                    kind="info",
                    title="Current inventory scope",
                ),
            ],
            gap=1.2,
        )
    return assets_view


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
def _(mo):
    maintenance_view = mo.vstack(
        [
            mo.md(
                "## Maintenance\n\n"
                "PHM finding 이후의 review/case/maintenance/post-validation 흐름을 위한 자리입니다."
            ),
            mo.hstack(
                [
                    mo.stat(
                        "Not connected",
                        label="Open cases",
                        caption="No maintenance case repository yet",
                    ),
                    mo.stat(
                        "Not connected",
                        label="Work orders",
                        caption="No CMMS/EAM integration yet",
                    ),
                    mo.stat(
                        "Not connected",
                        label="Maintenance history",
                        caption="No asset maintenance history source yet",
                    ),
                    mo.stat(
                        "Unavailable",
                        label="Post-maintenance validation",
                        caption="No completed maintenance event to validate",
                    ),
                ],
                widths="equal",
            ),
            mo.callout(
                "Future actions must preserve a human approval boundary. "
                "The current UI does not create or dispatch maintenance work.",
                kind="info",
                title="Action boundary",
            ),
        ],
        gap=1.2,
    )
    return maintenance_view


@app.cell
def _(mo, observation, timeline):
    if observation is None:
        source_health = "Not connected"
    elif timeline is None:
        source_health = f"Prepared snapshot validated · {observation.sample_count:,} samples"
    else:
        source_health = (
            f"Prepared history validated · {timeline.segment_count} segments · "
            f"latest {observation.sample_count:,} samples"
        )
    system_health_view = mo.vstack(
        [
            mo.md(
                "## System Health\n\n"
                "설비 상태와 플랫폼 상태를 혼동하지 않도록 별도 운영 관측 영역으로 둡니다."
            ),
            mo.hstack(
                [
                    mo.stat(
                        source_health,
                        label="Source",
                        caption="Prepared CSV snapshot/history, not live ingestion",
                    ),
                    mo.stat(
                        "Not instrumented",
                        label="Ingestion",
                        caption="No connector latency/backlog telemetry yet",
                    ),
                    mo.stat(
                        "Not connected",
                        label="Analysis runtime",
                        caption="No AnalysisRun producer/service connected yet",
                    ),
                    mo.stat(
                        "Not instrumented",
                        label="Telemetry",
                        caption="Logs / metrics / traces correlation is pending",
                    ),
                ],
                widths="equal",
            ),
            mo.callout(
                "Future telemetry will correlate source_id, asset_id, analysis_run_id and "
                "deployment_id. Until then this screen does not infer service health from "
                "the absence of PHM results.",
                kind="info",
                title="Observability boundary",
            ),
        ],
        gap=1.2,
    )
    return system_health_view


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
            "Field source bootstrap": mo.vstack(
                [
                    mo.md(
                        "현재 Operations prototype은 prepared single-asset CSV "
                        "snapshot 또는 동일 asset의 timestamped CSV history directory를 "
                        "application boundary를 통해 읽습니다. History directory가 "
                        "입력되면 single CSV보다 우선합니다. 등록 source는 Sources에서 "
                        "별도 persistent control-plane record로 확인할 수 있으며, 이 bootstrap은 "
                        "historian/API나 continuous ingestion을 대신하는 영구 제품 계약이 아닙니다."
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
    asset_view,
    assets_view,
    data_quality_view,
    investigation_view,
    maintenance_view,
    mo,
    overview_view,
    page_selector,
    source_setup,
    sources_view,
    system_health_view,
):
    views = {
        "Overview": overview_view,
        "Sources": sources_view,
        "Assets": assets_view,
        "Asset": asset_view,
        "Investigation": investigation_view,
        "Data Quality": data_quality_view,
        "Maintenance": maintenance_view,
        "System Health": system_health_view,
    }
    _header_items = [
        mo.md(
            "# PHM Operations\n\n"
            "설비 관측, 데이터 품질, PHM finding과 시스템 상태를 운영 관점에서 확인합니다."
        ),
        page_selector,
    ]
    if page_selector.value != "Sources":
        _header_items.append(source_setup)
    header = mo.vstack(_header_items, gap=1.0)
    mo.vstack([header, views[page_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
