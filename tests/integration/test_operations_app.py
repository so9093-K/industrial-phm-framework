"""Operations must render once analysis results and review requests exist."""

import runpy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SqlitePhaseUnbalanceRepository,
    create_human_review_finding,
)
from industrial_phm.apps import operations_app_path
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import OperationsWorkspace
from tests.support.window_analysis import END, phase_unbalance_analysis

OPERATIONS_APP = operations_app_path()


def _analysis():
    return phase_unbalance_analysis()


def _distinct_analysis(template, index: int):
    run_id = f"bounded-run-{index:04d}"
    reference = replace(template.evidence.input_reference, window_id=f"bounded-window-{index:04d}")
    return replace(
        template,
        run=replace(
            template.run,
            analysis_run_id=run_id,
            completed_at=template.run.completed_at + timedelta(seconds=index),
        ),
        evidence=replace(
            template.evidence,
            evidence_id=f"bounded-evidence-{index:04d}",
            analysis_run_id=run_id,
            input_reference=reference,
        ),
    )


def test_operations_empty_workspace_starts_with_first_run_landing(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["navigation_page"] == "setup"
    assert defs["monitor_workspace_ui"].widget.snapshot["page"] == "setup"
    assert defs["monitor_workspace_ui"].widget.snapshot["page_labels"]["setup"] == "Data connection"
    assert defs["first_run_mode"] == "landing"
    assert defs["first_run_sample_button"] is not None
    assert defs["first_run_real_button"] is not None
    assert "setup_section" not in defs


def test_operations_ko_locale_changes_display_without_changing_page_identity(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))
    monkeypatch.setenv("INDUSTRIAL_PHM_LOCALE", "ko-KR")

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    snapshot = defs["monitor_workspace_ui"].widget.snapshot
    assert defs["operations_locale"].value == "ko-KR"
    assert defs["navigation_page"] == "setup"
    assert snapshot["page"] == "setup"
    assert snapshot["page_labels"]["monitor"] == "관제"
    assert snapshot["page_labels"]["setup"] == "데이터 연결"
    assert snapshot["messages"]["monitor.refresh"] == "새로고침"
    assert defs["operations_text"]("first_run.sample.title", defs["operations_locale"]) == (
        "샘플 데이터로 둘러보기"
    )


def test_operations_registered_source_starts_in_monitor(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="acceptance-opcua",
            name="Acceptance OPC UA source",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="acceptance-pump",
                measurement_point_id="drive-end",
                node_mappings=(
                    OpcUaNodeMapping(
                        channel_id="vibration_x",
                        node_id="ns=2;s=Machine/VibrationX",
                    ),
                ),
                timeout_seconds=2.0,
            ),
            registered_at=datetime(2026, 10, 4, 3, 0, tzinfo=UTC),
        )
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["navigation_page"] == "monitor"
    assert defs["monitor_workspace_ui"].widget.snapshot["page"] == "monitor"
    assert defs["monitor_workspace_ui"].widget.snapshot["page_labels"]["monitor"] == "Monitor"
    assert defs["first_run_mode"] == "configured"
    assert "setup_section" not in defs
    assert "navigation" not in defs
    assert defs["monitor_range_id"] == "1h"
    assert defs["signal_range_selector"].value == "Live"
    assert defs["get_asset_section"]() == "overview"
    assert defs["get_investigation_review_filter"]() == "all"


def test_operations_renders_investigation_and_maintenance_queues(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(analysis)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["investigation_selected_id"] is not None
    assert defs["maintenance_selected_id"] is not None
    from industrial_phm.presentation.operations_navigation import resolve_operations_attention_route

    attention = next(item for item in defs["contextual_attention"] if item.finding_id)
    route = resolve_operations_attention_route(
        attention, investigation_queue=defs["investigation_queue"]
    )
    assert route.page == "investigations"
    assert "attention_view" not in defs
    assert "monitor_evidence_view" not in defs
    assert "monitor_signal_trends" not in defs


def test_operations_uses_single_workspace_environment(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(analysis)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    paths = defs["operations_context"].snapshot.paths
    assert paths.phase_analysis == workspace.phase_unbalance_state_path
    assert paths.history_catalog == workspace.history_catalog_path
    assert defs["investigation_selected_id"] is not None
    assert defs["maintenance_selected_id"] is not None


def test_operations_keeps_reviewed_result_outside_recent_limit(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    template = _analysis()
    result_store = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    oldest = None
    for index in range(502):
        result = _distinct_analysis(template, index)
        result_store.record(result)
        if index == 0:
            oldest = result
    assert oldest is not None
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(oldest)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    loaded_ids = {item.run.analysis_run_id for item in defs["analysis_results"]}
    assert "bounded-run-0000" in loaded_ids
    assert "bounded-run-0001" not in loaded_ids
    assert "bounded-run-0501" in loaded_ids
    queue_run_ids = {item.analysis_run_id for item in defs["investigation_queue"].items}
    assert "bounded-run-0000" in queue_run_ids


def test_review_request_updates_review_projections_without_reloading_state(tmp_path):
    import shutil

    from industrial_phm.runtime.operations_app_composition import (
        load_operations_app_snapshot,
        project_review_workflow,
    )

    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=END + timedelta(minutes=1),
    )
    (asset,) = (item for item in snapshot.monitor.assets if item.asset_id == "motor-7")
    assert asset.pending_review_count == 0
    assert not any(item.finding_id for item in snapshot.monitor.attention)

    # The projection reads nothing from disk: removing the workspace must not matter.
    shutil.rmtree(workspace.root)
    finding = create_human_review_finding(analysis)
    projection = project_review_workflow(snapshot, findings=(finding,), review_events=())

    (asset,) = (item for item in projection.monitor.assets if item.asset_id == "motor-7")
    assert asset.pending_review_count == 1
    assert [item.finding_id for item in projection.monitor.attention] == [finding.finding_id]
    assert projection.monitor.assessed_at == snapshot.assessed_at


def test_maintenance_review_reads_its_evidence_by_reference(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(analysis)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    evidence = defs["maintenance_evidence"]
    assert evidence is not None
    assert evidence.analysis_run_id == analysis.run.analysis_run_id
    assert evidence.observed_start_at == analysis.run.observed_start_at
    assert [row["quantity"] for row in defs["maintenance_evidence_metrics"]]
    assert defs["maintenance_open_investigation_button"] is not None
    # The persisted review keeps references only.
    stored = workspace.finding_state_path.read_text(encoding="utf-8")
    assert "median_percent" not in stored


@pytest.mark.parametrize(
    ("other_unit", "other_source", "expected_panels"),
    [
        ("A", "source", 1),
        ("V", "source", 2),
        ("A", "another-source", 2),
        (None, "source", 2),
        ("unknown", "source", 2),
    ],
)
def test_monitor_chart_overlays_only_known_compatible_measurements(
    other_unit, other_source, expected_panels
):
    import json

    from industrial_phm.application.measurement_history import (
        MultiSignalMeasurementHistoryAggregation,
        MultiSignalMeasurementHistoryBucket,
    )
    from industrial_phm.presentation.monitor_workspace import chart_payload

    at = datetime(2026, 10, 6, tzinfo=UTC)

    def bucket(channel, unit, source):
        return MultiSignalMeasurementHistoryBucket(
            channel_id=channel,
            source_id=source,
            source_type="opcua",
            measurement_point_id="point",
            bucket_start=at,
            bucket_end=at + timedelta(minutes=1),
            first_event_at=at,
            last_event_at=at,
            observation_count=1,
            usable_count=1,
            null_count=0,
            non_good_count=0,
            conflict_count=0,
            minimum=100.0,
            maximum=100.0,
            mean=100.0,
            interpretation_json=json.dumps(
                {"semantics": {"definition": {"observed_property": "phase current", "unit": unit}}}
            ),
        )

    result = MultiSignalMeasurementHistoryAggregation(
        start_at=at,
        end_at=at + timedelta(minutes=1),
        bucket_seconds=60,
        snapshot_id=1,
        buckets=(bucket("r", "A", "source"), bucket("s", other_unit, other_source)),
    )
    payload = chart_payload(result)
    assert payload is not None
    assert len(payload["groups"]) == expected_panels
    assert all(
        bucket["mean"] == 100.0
        for group in payload["groups"]
        for series in group["series"]
        for bucket in series["buckets"]
    )


def test_monitor_keeps_every_overlapping_evidence_and_routes_last_item(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    from industrial_phm.application.backfill import FileBackfillEvent
    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
    from industrial_phm.presentation.operations_navigation import resolve_investigation_route

    workspace = OperationsWorkspace(tmp_path / "workspace")
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="fixture",
            name="Evidence fixture",
            registered_at=END,
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="motor-7",
                node_mappings=(OpcUaNodeMapping(channel_id="va", node_id="ns=2;s=va"),),
            ),
        )
    )
    repository = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    for index in range(14):
        repository.record(_distinct_analysis(_analysis(), index))
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    history.append_file_batch(
        (
            FileBackfillEvent(
                raw_evidence_id="monitor-evidence-fixture",
                source_id="fixture",
                asset_id="motor-7",
                measurement_point_id="mcc-3",
                channel_id="va",
                source_file="fixture.csv",
                source_sha256="1" * 64,
                source_size_bytes=100,
                sample_index=0,
                event_at=END,
                value=220.0,
                source_metadata_json="{}",
            ),
        ),
        batch_id="monitor-evidence-fixture",
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))
    _, defs = runpy.run_path(str(OPERATIONS_APP))["app"].run()
    items = defs["monitor_window_evidence_items"]
    assert len(items) == 14
    snapshot = defs["monitor_workspace_ui"].widget.snapshot
    assert len(snapshot["evidence"]) == 14
    last_id = snapshot["evidence"][-1]["id"]
    route = resolve_investigation_route(last_id, investigation_queue=defs["investigation_queue"])
    assert route.investigation_id == last_id
