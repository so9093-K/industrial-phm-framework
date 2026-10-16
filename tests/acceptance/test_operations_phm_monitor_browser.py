"""Open the Monitor before new inputs; no manual refresh or mocked PHM results."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import T0, analyze, deliver, phm_workspace


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_monitor_discovers_inputs_waits_rejects_recovers_and_opens_exact_result(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    template = store.list_bindings()[0]
    store.create_binding(
        PhmBinding(
            "other-bearing",
            template.package_id,
            "other-source",
            "bearing-b",
            template.step_kind,
            T0,
        )
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                requests: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("request", lambda r: requests.append(r.url))
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#monitor")
                asset = page.locator('.monitor-asset[data-asset-id="bearing-a"]')
                other = page.locator('.monitor-asset[data-asset-id="bearing-b"]')
                pw.expect(asset).to_contain_text("입력 없음", timeout=15_000)
                pw.expect(page.locator(".monitor-asset")).to_have_count(2)
                pw.expect(page.locator(".monitor-model")).to_have_count(0)
                deliver(workspace, tmp_path / "waves", 1, 0.5)
                pw.expect(asset).to_contain_text("새 입력 분석 대기", timeout=10_000)
                pw.expect(asset).to_contain_text("입력 #1")
                # The actual waveform is visible before scoring, rather than hidden under models.
                pw.expect(page.locator("#monitor-signal-chart svg")).to_be_visible(timeout=10_000)
                analyze(workspace)
                pw.expect(asset).to_contain_text("기준 초과 없음", timeout=10_000)
                pw.expect(page.locator("#workspace-start")).not_to_be_visible()
                repo = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
                snapshot = repo.latest("bench", "bearing-a")
                assert snapshot is not None
                repo.record(replace(snapshot, source_id="other-source", asset_id="bearing-b"))
                analyze(workspace)
                pw.expect(other).to_contain_text("입력 #1", timeout=10_000)
                deliver(workspace, tmp_path / "waves", 2, 3.0)
                analyze(workspace)
                pw.expect(asset).to_contain_text("진동 변화 확인 필요", timeout=10_000)
                pw.expect(page.locator("#monitor-signal-reading")).to_contain_text("기록 #1 → #2")
                pw.expect(page.locator("#monitor-signal-reading")).to_contain_text("500% 커짐")
                detection = page.locator('.monitor-detection-result[data-binding-id="anomaly-a"]')
                pw.expect(detection).to_be_visible()
                pw.expect(detection).to_contain_text("이상 점수 증가")
                pw.expect(detection).to_contain_text("#1 → #2")
                pw.expect(page.locator("#monitor-score-chart")).not_to_be_visible()
                deliver(workspace, tmp_path / "waves", 3, 4.0)
                (tmp_path / "waves/3.csv").write_text("corrupted after delivery")
                analyze(workspace)
                pw.expect(asset).to_contain_text("최근 진동 파형을 읽을 수 없음", timeout=10_000)
                alert = page.locator('.monitor-attention-item[data-asset-id="bearing-a"]')
                pw.expect(alert).to_have_count(1)
                pw.expect(alert).to_contain_text("전달 후 원본 변경 감지")
                pw.expect(alert).to_contain_text("2개 분석")
                pw.expect(other).not_to_contain_text("최근 진동 파형을 읽을 수 없음")
                pw.expect(detection).to_contain_text("이전 결과 · 최신 입력 분석 전")
                pw.expect(page.locator("#monitor-signal-state")).to_contain_text(
                    "원본을 표시할 수 없습니다"
                )
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not any("/phm/series?" in r or "/condition?" in r for r in requests[10:])
                if width == 1440:
                    assert alert.bounding_box()["y"] < 900
                page.route("**/api/v1/phm/monitor", lambda r: r.fulfill(status=503, json={}))
                pw.expect(page.locator("#phm-monitor-state")).to_contain_text(
                    "PHM 조회 실패", timeout=10_000
                )
                pw.expect(page.locator(".monitor-asset")).to_have_count(0)
                pw.expect(page.locator("#monitor-signal-chart svg")).to_have_count(0)
                pw.expect(page.locator("#monitor-signal-reading")).not_to_be_visible()
                page.unroute("**/api/v1/phm/monitor")
                pw.expect(asset).to_contain_text("최근 진동 파형을 읽을 수 없음", timeout=10_000)
                asset.click()
                page.locator("#monitor-last-good").click()
                pw.expect(page.locator("#monitor-signal-context")).to_contain_text("이전 입력 · #2")
                pw.expect(page.locator("#monitor-signal-chart svg")).to_be_visible()
                page.locator("#monitor-analysis-details > summary").click()
                model = page.locator('.monitor-model[data-binding-id="anomaly-a"]')
                pw.expect(model).to_contain_text("이전 결과")
                model.get_by_role("link", name="이 시점의 추세·원본 입력 보기").click()
                pw.expect(page.locator("#anomaly-binding")).to_have_value("anomaly-a")
                pw.expect(page.locator("#anomaly-detail h3")).to_contain_text("획득 #2")
                pw.expect(page.locator("#anomaly-detail .phm-wave")).to_have_count(2)
                page.reload()
                pw.expect(page.locator("#anomaly-detail h3")).to_contain_text("획득 #2")
                pw.expect(page.locator("#anomaly-explanation h3")).to_contain_text("분석 #2")
                # A keyboard-selected older record updates summary, raw input and bookmark together.
                page.locator("#anomaly-position").focus()
                page.locator("#anomaly-position").press("ArrowUp")
                pw.expect(page.locator("#anomaly-detail h3")).to_contain_text("획득 #1")
                pw.expect(page.locator("#anomaly-observation")).to_contain_text(
                    "선택한 이전 기록 #1"
                )
                assert "phm_position=1" in page.url
                page.select_option("#anomaly-position", "2")
                pw.expect(page.locator("#anomaly-detail h3")).to_contain_text("획득 #2")
                # A bookmark of the other model's result opens that model at that record.
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?phm_binding=anomaly-b&phm_position=2&phm_view=anomaly#anomaly"
                )
                pw.expect(page.locator("#anomaly-binding")).to_have_value("anomaly-b")
                pw.expect(page.locator("#anomaly-position")).to_have_value("2")
                page.reload()
                pw.expect(page.locator("#anomaly-position")).to_have_value("2")
                # A real refused bookmark cannot substitute the last successful score.
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?phm_binding=anomaly-a&phm_position=3#anomaly"
                )
                pw.expect(page.locator("#anomaly-state")).to_contain_text("선택한 기록 #3")
                pw.expect(page.locator("#anomaly-cards>*")).to_have_count(0)
                pw.expect(page.locator("#anomaly-score-chart svg")).to_have_count(0)
                # An unknown target cannot silently open another asset/model.
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?phm_binding=missing&phm_position=2#anomaly"
                )
                pw.expect(page.locator("#anomaly-state")).to_contain_text("읽지 못했습니다")
                pw.expect(page.locator("#anomaly-cards>*")).to_have_count(0)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [390, 1440])
def test_attention_actions_open_the_matching_problem_with_visible_context(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    from industrial_phm.application import JsonSourceRepository, OpcUaSourceConfig, RegisteredSource
    from industrial_phm.connectors import OpcUaNodeMapping
    from industrial_phm.runtime.operations_web_phm_explanation import request_phm_review

    workspace = phm_workspace(tmp_path / "ws")
    registry = JsonSourceRepository(workspace.source_registry_path)
    for source, asset in (("compressor-link", "compressor-01"), ("other-link", "compressor-02")):
        registry.register(
            RegisteredSource(
                source,
                source,
                OpcUaSourceConfig(
                    "opc.tcp://127.0.0.1:4840",
                    asset,
                    (OpcUaNodeMapping(channel_id="pressure", node_id="ns=2;s=pressure"),),
                ),
                T0,
            )
        )
    for ordinal, scale in enumerate((0.5, 3.0), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    request_phm_review(
        workspace.root, {"binding_id": "anomaly-a", "position": 2, "explanation_id": None}
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/"
                page.goto(base + "#monitor")
                alert = page.locator('.monitor-attention-item[data-asset-id="bearing-a"]')
                change_action = alert.get_by_role("link", name="신호 변화 확인")
                change_action.focus()
                old_action = change_action.element_handle()
                # Periodic refresh may rebuild cards, but must keep keyboard focus.
                with page.expect_response("**/api/v1/phm/monitor"):
                    pw.expect(change_action).to_be_focused()
                page.wait_for_function("old => !old.isConnected", arg=old_action)
                pw.expect(change_action).to_be_focused()
                change_action.press("Enter")
                pw.expect(page.locator("#anomaly-binding")).to_have_value("anomaly-a")
                pw.expect(page.locator("#anomaly-position")).to_have_value("2")
                pw.expect(page.locator("#anomaly-observation")).to_contain_text("높아졌습니다")
                pw.expect(page.locator("#anomaly-meaning")).to_contain_text("기준을 넘었습니다")
                pw.expect(page.locator("#anomaly-meaning")).to_contain_text("모델 기준")
                page.goto(base + "#monitor")
                alert.get_by_role("link", name="검토 기록 확인").click()
                panel = page.locator("#anomaly-explanation")
                pw.expect(panel).to_be_focused()
                pw.expect(panel).to_contain_text("분석 #2")
                pw.expect(panel.locator(".phm-review-status")).to_contain_text("확인 대기")
                pw.expect(panel.locator(".phm-review-help")).to_contain_text("담당자")
                page.goto(base + "#monitor")
                receipt = page.locator('.monitor-attention-item[data-asset-id="compressor-01"]')
                receipt.get_by_role("link", name="데이터 연결 상태 확인").click()
                connection = page.locator('.source-record[data-source-id="compressor-link"]')
                pw.expect(connection).to_be_focused()
                pw.expect(connection.locator(".source-diagnostics")).to_have_attribute("open", "")
                assert "connect_source=compressor-link" in page.url
                box = connection.bounding_box()
                assert box and 0 <= box["y"] < 900
                pw.expect(page.locator("#asset-switch")).to_have_value("compressor-01")
                # A different source must not stand in for a missing connection.
                page.goto(base + "?connect_asset=compressor-01&connect_source=missing#connect")
                pw.expect(page.locator("#source-status")).to_contain_text(
                    "선택한 연결을 찾지 못했습니다"
                )
                page.goto(base + "#monitor")
                deliver(workspace, tmp_path / "waves", 3, 4.0)
                (tmp_path / "waves/3.csv").write_text("corrupted after delivery")
                analyze(workspace)
                alert.get_by_role("button", name="분석 입력·모델 확인").click()
                model = page.locator('.monitor-model[data-binding-id="anomaly-a"]')
                pw.expect(model).to_be_focused()
                pw.expect(model).to_contain_text("분석 거부")
                pw.expect(model.locator("details")).to_have_attribute("open", "")
                # A background refresh may replace the model article: retain the
                # operator's focus and expanded evidence on the same binding.
                with page.expect_response("**/api/v1/phm/monitor"):
                    pw.expect(model).to_be_focused()
                pw.expect(model).to_be_focused()
                pw.expect(model.locator("details")).to_have_attribute("open", "")
                box = model.bounding_box()
                assert box and 0 <= box["y"] < 900
                deliver(workspace, tmp_path / "waves", 4, 0.6)
                alert.get_by_role("button", name="분석 진행 확인").click()
                pw.expect(model).to_contain_text("새 입력 분석 대기")
                page.goto(base + "?phm_binding=anomaly-b&phm_position=1&phm_view=anomaly#anomaly")
                pw.expect(page.locator("#anomaly-position")).to_have_value("1")
                pw.expect(page.locator("#anomaly-position")).to_be_enabled()
                page.locator("#anomaly-position").focus()
                with page.expect_response("**/api/v1/phm/series?*"):
                    pw.expect(page.locator("#anomaly-position")).to_be_focused()
                pw.expect(page.locator("#anomaly-position")).to_be_focused()
                page.locator("#anomaly-position").press("ArrowDown")
                pw.expect(page.locator("#anomaly-position")).to_have_value("2")
                assert "phm_position=2" in page.url
                page.reload()
                pw.expect(page.locator("#anomaly-position")).to_have_value("2")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
