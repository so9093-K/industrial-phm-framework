"""An asset without a model gets one connected from its anomaly tab, and results follow."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_config import (
    OperationsUiConfig,
    write_operations_runtime_config,
)
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_web_phm_models import project_phm_models
from tests.acceptance.test_operations_web_controlled_journey_browser import _port, _start, _stop
from tests.support.phm import T0, analyze, deliver, phm_workspace


class _InProcessSupervisor:
    """Executes authorized actions the way the supervisor broker does, without IPC."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        return execute_web_source_action(self.root, route, payload)


@pytest.mark.parametrize("width", [390, 1440])
def test_connecting_a_model_from_the_anomaly_tab_shows_its_scores(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    root = workspace.root.resolve()
    server = create_operations_web_read_server(root, command_client=_InProcessSupervisor(root))  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a"
                page.goto(base + "#anomaly")
                panel = page.locator("#anomaly-connect")
                pw.expect(panel).to_contain_text("연결할 수 있는 이상 탐지 모델")
                pw.expect(panel).to_contain_text("synthetic-vertical-score-v1")
                panel.get_by_role("button", name="진동 변화 탐지 모델 연결").first.click()
                pw.expect(page.locator("#anomaly-binding")).to_be_enabled()
                pw.expect(panel).to_be_empty()
                pw.expect(page.locator("#anomaly-state")).to_contain_text("저장된 입력 분석 대기")

                analyze(workspace)
                pw.expect(page.locator("#anomaly-state")).to_contain_text("4개 step 분석")
                pw.expect(page.locator("#anomaly-cards > *").first).to_be_visible()
                assert errors == []
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_large_saved_csv_keeps_analysis_limit_and_measured_signal_available(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    from industrial_phm.runtime.operations_workspace import (
        OperationsWorkspace,
        initialize_operations_workspace,
    )

    workspace = OperationsWorkspace(tmp_path / "ws")
    init = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(init.config, ui=OperationsUiConfig(port=port))
    )
    path = tmp_path / "large.csv"
    path.write_text(
        "timestamp,current,note\n"
        + "".join(f"2026-10-14T01:00:{i:02d}+00:00,{i + 1},{'a' * 100000}\n" for i in range(12))
    )
    assert path.stat().st_size > 1024 * 1024
    proc = _start(workspace.root, port, tmp_path / "supervisor.log")
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(locale="ko-KR", viewport={"width": 390, "height": 844})
                page.goto(f"http://127.0.0.1:{port}/web/#connect")
                page.locator("#csv-start-file").set_input_files(path)
                page.locator("#csv-start-asset").fill("motor-large")
                page.get_by_role("button", name="서버에서 파일 점검 (저장 안 함)").click()
                pw.expect(page.locator("#csv-start-save")).to_be_enabled(timeout=15000)
                page.locator("#csv-start-save").click()
                pw.expect(page.locator("#csv-start-done")).to_be_visible(timeout=30000)
                pw.expect(page.locator("#csv-start-analyze")).to_be_visible()
                pw.expect(page.locator("#csv-start-analyze")).to_be_disabled()
                pw.expect(page.locator("#csv-start-analysis-limit")).to_contain_text("1 MiB")
                pw.expect(page.locator("#csv-start-analysis-limit")).to_contain_text("구간")
                page.locator("#csv-start-open-monitor").click()
                pw.expect(page.locator("#monitor-signal-reading")).to_contain_text(
                    "12", timeout=15000
                )
                pw.expect(page.locator("#monitor-signal-chart svg")).to_be_visible()
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)


def test_supervised_runner_analyzes_a_web_connection_without_a_manual_analysis_call(
    tmp_path: Path,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    deliver(workspace, tmp_path / "waves", 1, 0.5)
    port = _port()
    from industrial_phm.runtime.operations_config import load_operations_runtime_config

    config = load_operations_runtime_config(workspace.config_path)
    write_operations_runtime_config(
        workspace.config_path, replace(config, ui=OperationsUiConfig(port=port))
    )
    proc = _start(workspace.root, port, tmp_path / "supervisor.log")
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(locale="ko-KR")
                page.goto(f"http://127.0.0.1:{port}/web/?monitor_asset=bearing-a#anomaly")
                page.get_by_role("button", name="진동 변화 탐지 모델 연결").first.click()
                pw.expect(page.locator("#anomaly-cards > *").first).to_be_visible(timeout=15000)
                pw.expect(page.locator("#asset-switch")).to_have_value("bearing-a")
                store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
                (binding,) = store.list_bindings()
                assert store.get_result(binding.binding_id, 1).state.value == "analyzed"
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)


def test_delayed_model_candidates_do_not_replace_the_newly_selected_asset(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    deliver(workspace, tmp_path / "waves", 1, 0.5)
    models = project_phm_models(workspace, "bearing-a")
    # pump-b has stored measurements but no model input stream.
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:pump:{'f' * 64}:{index}",
                source_id="pump-file",
                asset_id="pump-b",
                channel_id="current",
                source_file="pump.csv",
                source_sha256="f" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=T0 + timedelta(minutes=index),
                value=1.0 + index,
            )
            for index in range(5)
        ),
        batch_id="pump",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(locale="ko-KR")
                held = []
                page.route(
                    "**/api/v1/phm/models?asset_id=bearing-a", lambda route: held.append(route)
                )
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a#anomaly"
                )
                pw.expect(page.locator("#anomaly-connect")).to_contain_text("모델을 확인")
                pw.expect(page.locator("#asset-switch option[value='pump-b']")).to_have_count(1)
                page.locator("#asset-switch").select_option("pump-b")
                pw.expect(page.locator("#anomaly-connect")).to_contain_text("모델 입력으로 쓸")
                assert held
                for route in held:
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(models)
                    )
                page.wait_for_timeout(200)
                pw.expect(page.locator("#anomaly-connect")).not_to_contain_text(
                    "synthetic-rms-score"
                )
                pw.expect(page.locator("#anomaly-connect button")).to_have_count(0)
                pw.expect(page.locator("#asset-switch")).to_have_value("pump-b")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
