import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo

    from industrial_phm.adapters import CsvSensorLayout, CsvSensorSourceError
    from industrial_phm.application import (
        AssetObservationSummary,
        load_field_csv_observation_summary,
    )
    from industrial_phm.contracts import DataQualityState

    return (
        AssetObservationSummary,
        CsvSensorLayout,
        CsvSensorSourceError,
        DataQualityState,
        Path,
        load_field_csv_observation_summary,
        mo,
        os,
    )


@app.cell
def _(CsvSensorLayout, CsvSensorSourceError, Path, load_field_csv_observation_summary):
    def parse_channels(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def parse_sampling_rate(value: str) -> float | None:
        return None if not value.strip() else float(value)

    def load_observation(
        *,
        source_path: str,
        asset_id: str,
        source_id: str,
        measurement_point_id: str,
        channels: str,
        timestamp_column: str,
        sampling_rate_hz: str,
    ):
        path_value = source_path.strip()
        if not path_value:
            return None, ""

        try:
            summary = load_field_csv_observation_summary(
                Path(path_value),
                CsvSensorLayout(
                    asset_id=asset_id.strip(),
                    timestamp_column=timestamp_column.strip() or None,
                    channel_columns=parse_channels(channels),
                    sampling_rate_hz=parse_sampling_rate(sampling_rate_hz),
                ),
                source_id=source_id.strip(),
                measurement_point_id=measurement_point_id.strip() or None,
            )
        except (CsvSensorSourceError, OSError, ValueError) as error:
            return None, str(error)

        return summary, ""

    return load_observation, parse_channels, parse_sampling_rate


@app.cell
def _(load_observation, os):
    source_default = os.environ.get("INDUSTRIAL_PHM_OPERATIONS_SOURCE", "")
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

    initial_summary, initial_error = load_observation(
        source_path=source_default,
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
        initial_error,
        initial_summary,
        measurement_point_default,
        sampling_rate_default,
        source_default,
        source_id_default,
        timestamp_default,
    )


@app.cell
def _(
    asset_default,
    channels_default,
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
        load_button,
        measurement_point_input,
        page_selector,
        sampling_rate_input,
        source_id_input,
        source_input,
        timestamp_input,
    )


@app.cell
def _(initial_error, initial_summary, mo):
    get_observation, set_observation = mo.state(initial_summary)
    get_load_error, set_load_error = mo.state(initial_error)
    return get_load_error, get_observation, set_load_error, set_observation


@app.cell
def _(
    asset_input,
    channels_input,
    load_button,
    load_observation,
    measurement_point_input,
    sampling_rate_input,
    set_load_error,
    set_observation,
    source_id_input,
    source_input,
    timestamp_input,
):
    if load_button.value:
        _summary, _error = load_observation(
            source_path=source_input.value,
            asset_id=asset_input.value,
            source_id=source_id_input.value,
            measurement_point_id=measurement_point_input.value,
            channels=channels_input.value,
            timestamp_column=timestamp_input.value,
            sampling_rate_hz=sampling_rate_input.value,
        )
        set_observation(_summary)
        set_load_error(_error)
    return


@app.cell
def _(get_load_error, get_observation):
    observation = get_observation()
    load_error = get_load_error()
    return load_error, observation


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
def _(load_error, mo, observation):
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
def _(mo, observation, observation_detail, quality_view):
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
def _(mo):
    investigation_view = mo.vstack(
        [
            mo.md(
                "## Investigation\n\n"
                "관측 사실과 PHM evidence를 같은 흐름에서 검토하기 위한 운영 surface입니다."
            ),
            mo.callout(
                "No operational finding is selected because no validated field finding "
                "pipeline is connected yet.",
                kind="neutral",
                title="Finding · Unavailable",
            ),
            mo.callout(
                "Anomaly/condition trend will appear here only after a field analysis "
                "run produces evidence with validated operational semantics.",
                kind="neutral",
                title="Trend & Evidence · Unavailable",
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
                    "The current field bootstrap exposes one asset segment at a time. "
                    "A one-row inventory is a source limitation, not the final fleet model.",
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
def _(mo, observation):
    source_health = (
        "Not connected"
        if observation is None
        else f"Prepared snapshot validated · {observation.sample_count:,} samples"
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
                        caption="Current bootstrap is prepared CSV, not live ingestion",
                    ),
                    mo.stat(
                        "Not instrumented",
                        label="Ingestion",
                        caption="No connector latency/backlog telemetry yet",
                    ),
                    mo.stat(
                        "Not connected",
                        label="Analysis runtime",
                        caption="No operational analysis service yet",
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
                        "현재 Operations prototype은 prepared single-asset CSV를 "
                        "application boundary를 통해 읽습니다. "
                        "이 입력은 historian/API를 대신하는 영구 제품 계약이 아닙니다."
                    ),
                    source_input,
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
    system_health_view,
):
    views = {
        "Overview": overview_view,
        "Assets": assets_view,
        "Asset": asset_view,
        "Investigation": investigation_view,
        "Data Quality": data_quality_view,
        "Maintenance": maintenance_view,
        "System Health": system_health_view,
    }
    header = mo.vstack(
        [
            mo.md(
                "# PHM Operations\n\n"
                "설비 관측, 데이터 품질, PHM finding과 시스템 상태를 운영 관점에서 확인합니다."
            ),
            page_selector,
            source_setup,
        ],
        gap=1.0,
    )
    mo.vstack([header, views[page_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
