"""Chromium acceptance for the opt-in, real-data read-only Web monitor.

This does not launch or switch the supervised marimo Operations product.
A real FILE→DuckLake ingestion is queried through the same local HTTP routes
that the packaged browser JS fetches. No mocked API, diagnostic or live claim.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    RegisteredSource,
    SqlitePhaseUnbalanceRepository,
    backfill_registered_file_source,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_command import (
    WebCommandClient,
    open_supervisor_web_command_broker,
)
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.window_analysis import phase_unbalance_analysis


@pytest.mark.parametrize("width", [1024, 1440])
def test_web_monitor_reads_actual_stored_signals_in_browser(tmp_path: Path, width: int) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = OperationsWorkspace(tmp_path / "actual-data")
    initialize_operations_workspace(workspace)
    event_at = datetime.now(UTC) - timedelta(minutes=3)
    source_path = tmp_path / "real-observations.csv"
    source_path.write_text(
        "time,phase-R,phase-S,phase-T\n"
        f"{event_at.isoformat()},220.5,219.3,220.1\n"
        f"{(event_at + timedelta(seconds=1)).isoformat()},220.7,219.4,220.2\n",
        encoding="utf-8",
    )
    source = RegisteredSource(
        source_id="test-phase-source",
        name="실제 FILE 측정",
        config=FileSourceConfig(
            source_path=str(source_path),
            asset_id="pump-01",
            measurement_point_id="panel-main",
            channel_columns=("phase-R", "phase-S", "phase-T"),
            timestamp_column="time",
        ),
        registered_at=event_at - timedelta(minutes=1),
    )
    JsonSourceRepository(workspace.source_registry_path).register(source)
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=workspace.history_catalog_path,
            data_path=workspace.history_data_path,
        )
    )
    assert (
        backfill_registered_file_source(
            JsonSourceRepository(workspace.source_registry_path), repository, source.source_id
        ).event_count
        == 6
    )

    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors: list[str] = []
            external: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on(
                "request",
                lambda req: (
                    external.append(req.url)
                    if not req.url.startswith(f"http://127.0.0.1:{server.server_port}/")
                    else None
                ),
            )
            page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
            sync_api.expect(page.get_by_role("heading", name="설비 모니터링")).to_be_visible()
            # The first keyboard stop on a new page is the visible skip link.
            page.keyboard.press("Tab")
            sync_api.expect(page.locator(".skip-link")).to_be_focused()
            page.keyboard.press("Enter")
            sync_api.expect(page.locator("#main")).to_be_focused()
            assert page.evaluate("location.hash") == "#main"
            # English guidance is a separate language-tagged reference, not an English UI.
            guide = page.locator("#operator-reference-en")
            sync_api.expect(guide.locator("summary")).to_have_attribute("lang", "en")
            assert page.locator("html").get_attribute("lang") == "ko"
            guide.locator("summary").focus()
            page.keyboard.press("Enter")
            sync_api.expect(guide).to_have_attribute("open", "")
            sync_api.expect(guide.locator('div[lang="en"]')).to_contain_text("Registered / active:")
            sync_api.expect(guide.locator('div[lang="en"]')).to_contain_text(
                "Review acknowledged / closed:"
            )
            sync_api.expect(guide.locator('div[lang="en"]')).to_contain_text(
                "not an English-language operations interface"
            )
            # Keyboard activation, not a mouse click, must update current navigation.
            page.get_by_role("link", name="시스템 근거").focus()
            page.keyboard.press("Enter")
            assert page.evaluate("location.hash") == "#system"
            sync_api.expect(page.get_by_role("combobox", name="설비 ID")).to_be_visible()
            page.get_by_role("link", name="시스템 근거").click()
            sync_api.expect(page.locator('nav a[href="#system"]')).to_have_attribute(
                "aria-current", "page"
            )
            sync_api.expect(page.locator("#system-status")).to_contain_text(
                "수집기 가동·실시간 연결·설비 정상 또는 안전 판정이 아닙니다"
            )
            sync_api.expect(page.locator("#system-facts")).to_contain_text("조회 평가 시각 · UTC")
            sync_api.expect(page.locator("#asset-select")).to_have_value("pump-01")
            sync_api.expect(page.locator("#channel-options input:checked")).to_have_count(1)
            sync_api.expect(page.locator("#last-values .latest-item")).to_have_count(1)
            sync_api.expect(page.locator("#trend-results .trend-dot").first).to_be_visible()
            sync_api.expect(page.locator("#last-values")).to_contain_text("220.7")
            sync_api.expect(page.locator("#last-values")).to_contain_text("unknown")
            # Two more phase signals use the same bounded server-side history API.
            page.locator('#channel-options input[value="phase-S"]').check()
            page.locator('#channel-options input[value="phase-T"]').check()
            page.get_by_role("button", name="신호 이력 확인").click()
            sync_api.expect(page.locator("#last-values .latest-item")).to_have_count(3)
            sync_api.expect(page.locator("#trend-results .trend-group")).to_have_count(3)
            sync_api.expect(page.locator("#evidence-results")).to_contain_text(
                "분석 기록이 없습니다"
            )
            sync_api.expect(page.locator("#review-results")).to_contain_text("검토 요청이 없습니다")
            # Fail the real monitor HTTP request after a populated read. The browser
            # must discard stale facts rather than present them as current evidence.
            page.route("**/api/v1/monitor", lambda route: route.abort("failed"))
            page.get_by_role("button", name="데이터 다시 불러오기").click()
            sync_api.expect(page.locator("#system-status")).to_contain_text(
                "시스템 조회 실패 · 정상 상태로 판단할 수 없습니다"
            )
            sync_api.expect(page.locator("#system-facts .fact")).to_have_count(0)
            sync_api.expect(page.locator("#asset-count")).to_have_text("—")
            sync_api.expect(page.locator("#asset-select")).to_be_disabled()
            sync_api.expect(page.locator("#last-values .latest-item")).to_have_count(0)
            sync_api.expect(page.locator("#review-results")).to_contain_text(
                "조회 실패 · 이전 데이터를 현재 상태로 표시하지 않습니다"
            )
            # Recover the transport, then require a new server-backed snapshot.
            page.unroute("**/api/v1/monitor")
            sync_api.expect(page.get_by_role("button", name="데이터 다시 불러오기")).to_be_enabled()
            page.get_by_role("button", name="데이터 다시 불러오기").click()
            sync_api.expect(page.locator("#system-status")).to_contain_text(
                "저장소 오류 범위가 보고되지 않았습니다"
            )
            sync_api.expect(page.locator("#system-facts")).to_contain_text("조회된 설비 수")
            sync_api.expect(page.locator("#asset-select")).to_have_value("pump-01")
            sync_api.expect(page.locator("#last-values")).to_contain_text("220.7")
            assert not errors, errors
            assert not external, external
            metrics = page.evaluate(
                "() => ({viewport: innerWidth, scroll: document.documentElement.scrollWidth})"
            )
            assert metrics["scroll"] <= metrics["viewport"] + 2, metrics
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_web_monitor_empty_workspace_has_no_fake_equipment(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "empty")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1024, "height": 800})
            page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
            sync_api.expect(page.locator("#asset-select")).to_be_disabled()
            sync_api.expect(page.locator("#system-status")).to_contain_text(
                "수집기 가동·실시간 연결·설비 정상 또는 안전 판정이 아닙니다"
            )
            sync_api.expect(page.locator("#system-facts")).to_contain_text("조회된 설비 수")
            sync_api.expect(page.locator("#asset-facts")).to_contain_text("설비가 없습니다")
            sync_api.expect(page.locator("#last-values .latest-item")).to_have_count(0)
            assert "현재 설비 정상" not in page.locator("body").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [1024, 1440])
def test_first_run_registers_prepared_file_without_faking_receipt(
    tmp_path: Path, width: int
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "first-run")
    initialize_operations_workspace(workspace)
    input_dir = workspace.root / "inputs"
    input_dir.mkdir()
    (input_dir / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-08T11:50:00+00:00,221.0,219.5,220.6\n"
        "2026-10-08T11:50:01+00:00,221.1,219.6,220.7\n",
        encoding="utf-8",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
            sync_api.expect(page.locator("#onboarding-state")).to_contain_text("소스 미등록")
            page.locator('#file-form input[name="source_id"]').fill("web-file-01")
            page.locator('#file-form input[name="name"]').fill("웹 등록 CSV")
            page.locator('#file-form input[name="asset_id"]').fill("pump-01")
            page.locator('#file-form input[name="measurement_point_id"]').fill("panel")
            page.locator('input[name="file_path"]').fill("inputs/phase.csv")
            page.locator('input[name="channel_columns"]').fill("phase-R,phase-S,phase-T")
            page.locator('input[name="timestamp_column"]').fill("timestamp")
            page.get_by_role("button", name="CSV 확인 후 소스 등록").click()
            sync_api.expect(page.locator("#register-result")).to_contain_text(
                "등록 완료 · 수신 근거 미확인"
            )
            sync_api.expect(page.locator("#source-list")).to_contain_text("web-file-01")
            sync_api.expect(page.locator("#source-list")).to_contain_text("수신 근거 미확인")
            sync_api.expect(page.locator("#onboarding-state")).to_contain_text("수신 확인 0개")
            sync_api.expect(page.locator("#asset-select")).to_have_value("pump-01")
            assert (
                JsonSourceRepository(workspace.source_registry_path).get("web-file-01").asset_id
                == "pump-01"
            )
            assert not page.locator("#last-values .latest-item").count()
            assert not errors, errors
            width_info = page.evaluate(
                "() => ({viewport: innerWidth, scroll: document.documentElement.scrollWidth})"
            )
            assert width_info["scroll"] <= width_info["viewport"] + 2
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_opcua_web_control_requests_do_not_claim_live_receipts(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from industrial_phm.application import OpcUaSourceConfig
    from industrial_phm.connectors import OpcUaNodeMapping
    from industrial_phm.runtime.collection_control import SqliteCollectionControlRepository

    workspace = OperationsWorkspace(tmp_path / "control-ui")
    initialize_operations_workspace(workspace)
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="web-opcua",
            name="Web OPC UA control",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="motor-01",
                node_mappings=(OpcUaNodeMapping(channel_id="v-r", node_id="ns=2;s=V_R"),),
            ),
            registered_at=datetime.now(UTC),
        )
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1024, "height": 900})
            page.goto(
                f"http://127.0.0.1:{server.server_port}/web/",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            listing = page.locator("#source-list")
            sync_api.expect(listing).to_contain_text("수신 근거 미확인")
            page.on("dialog", lambda dialog: dialog.accept())
            listing.get_by_role("button", name="소스 활성화").click()
            sync_api.expect(listing).to_contain_text("관리 상태: active")
            # A failed monitor refresh must not turn a persisted control request
            # into a reported mutation failure.
            page.route(
                "**/api/v1/monitor",
                lambda route: route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":{"code":"history_or_snapshot_unavailable"}}',
                ),
            )
            listing.get_by_role("button", name="수집 시작 요청").click()
            sync_api.expect(listing).to_contain_text("연속 수집 요청: running")
            sync_api.expect(page.locator("#source-control-result")).to_contain_text(
                "수집 상태 요청 저장됨"
            )
            sync_api.expect(page.locator("#notice")).to_contain_text(
                "이력 저장소를 확인할 수 없습니다"
            )
            sync_api.expect(listing).to_contain_text("수신 근거 미확인")
            stored = SqliteCollectionControlRepository(workspace.collection_control_path).get(
                "web-opcua"
            )
            assert stored is not None and stored.desired_state.value == "running"
            assert not page.locator("#last-values .latest-item").count()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_web_file_receipt_browser_keeps_history_separate(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from industrial_phm.application import JsonSourceRuntimeRepository

    workspace = OperationsWorkspace(tmp_path / "file-receipt-browser")
    initialize_operations_workspace(workspace)
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n2026-10-08T12:00:00+00:00,220,219,221\n",
        encoding="utf-8",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1024, "height": 900})
            page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
            page.locator('#file-form input[name="source_id"]').fill("file-receipt")
            page.locator('#file-form input[name="name"]').fill("FILE receipt")
            page.locator('#file-form input[name="asset_id"]').fill("pump-01")
            page.locator('input[name="file_path"]').fill("inputs/phase.csv")
            page.locator('input[name="channel_columns"]').fill("phase-R,phase-S,phase-T")
            page.locator('input[name="timestamp_column"]').fill("timestamp")
            page.get_by_role("button", name="CSV 확인 후 소스 등록").click()
            sync_api.expect(page.locator("#source-list")).to_contain_text("수신 근거 미확인")
            page.on("dialog", lambda dialog: dialog.accept())
            page.locator("#source-list").get_by_role("button", name="소스 활성화").click()
            sync_api.expect(page.locator("#source-list")).to_contain_text("관리 상태: active")
            page.locator("#source-list").get_by_role("button", name="FILE 수신 확인").click()
            sync_api.expect(page.locator("#source-control-result")).to_contain_text(
                "FILE 검증 수신 근거 기록 완료"
            )
            sync_api.expect(page.locator("#source-list")).to_contain_text(
                "FILE 검증 수신 근거 있음"
            )
            sync_api.expect(page.locator("#onboarding-state")).to_contain_text(
                "저장된 시계열은 별도로 확인해야 합니다"
            )
            assert (
                JsonSourceRuntimeRepository(workspace.source_runtime_path).get_latest_receipt(
                    "file-receipt"
                )
                is not None
            )
            assert not workspace.history_catalog_path.exists()
            assert not page.locator("#last-values .latest-item").count()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [1024, 1440])
def test_web_file_backfill_browser_shows_actual_stored_history(tmp_path: Path, width: int) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")
    workspace = OperationsWorkspace(tmp_path / "file-web-history")
    initialize_operations_workspace(workspace)
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    observed = datetime.now(UTC) - timedelta(minutes=2)
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        f"{observed.isoformat()},220.5,219.0,221.0\n"
        f"{(observed + timedelta(seconds=1)).isoformat()},220.7,219.2,221.1\n",
        encoding="utf-8",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
            page.locator('#file-form input[name="source_id"]').fill("web-history-01")
            page.locator('#file-form input[name="name"]').fill("FILE history")
            page.locator('#file-form input[name="asset_id"]').fill("pump-01")
            page.locator('input[name="file_path"]').fill("inputs/phase.csv")
            page.locator('input[name="channel_columns"]').fill("phase-R,phase-S,phase-T")
            page.locator('input[name="timestamp_column"]').fill("timestamp")
            page.get_by_role("button", name="CSV 확인 후 소스 등록").click()
            listing = page.locator("#source-list")
            sync_api.expect(listing).to_contain_text("web-history-01")
            page.on("dialog", lambda dialog: dialog.accept())
            listing.get_by_role("button", name="소스 활성화").click()
            sync_api.expect(listing).to_contain_text("관리 상태: active")
            page.locator("#source-list").get_by_role("button", name="FILE 수신 확인").click()
            sync_api.expect(listing).to_contain_text("FILE 검증 수신 근거 있음")
            assert not workspace.history_catalog_path.exists()
            listing.get_by_role("button", name="FILE 이력 적재").click()
            sync_api.expect(page.locator("#source-control-result")).to_contain_text(
                "DuckLake 이력 적재 완료"
            )
            sync_api.expect(page.locator("#source-control-result")).to_contain_text("6개 이벤트")
            sync_api.expect(page.locator("#last-values")).to_contain_text("220.7")
            assert workspace.history_catalog_path.exists()
            listing.get_by_role("button", name="FILE 이력 적재").click()
            sync_api.expect(page.locator("#source-control-result")).to_contain_text(
                "재사용 배치 1개"
            )
            assert not errors, errors
            geometry = page.evaluate(
                "() => ({width: innerWidth, scroll: document.documentElement.scrollWidth})"
            )
            assert geometry["scroll"] <= geometry["width"] + 2
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [1024, 1440])
def test_web_review_buttons_follow_persisted_evidence_in_browser(
    tmp_path: Path, width: int
) -> None:
    """Real Chromium → Web POST → PID-bound broker → review repository integration."""
    sync_api = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = OperationsWorkspace(tmp_path / "review-ui")
    initialize_operations_workspace(workspace)
    phase = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(phase)
    source_path = tmp_path / "registered.csv"
    source_path.write_text("time,va\n2026-09-29T12:00:00+00:00,220.0\n", encoding="utf-8")
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="test-source",
            name="Reference source for review UI",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id=phase.run.asset_id,
                measurement_point_id=phase.run.measurement_point_id,
                channel_columns=("va",),
                timestamp_column="time",
            ),
            registered_at=phase.run.completed_at,
        )
    )
    with open_supervisor_web_command_broker(workspace.root) as broker:
        broker.bind_child(os.getpid())
        client = WebCommandClient(broker.socket_path, broker.token)
        server = create_operations_web_read_server(workspace.root, command_client=client)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_api.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                external: list[str] = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.on(
                    "request",
                    lambda request: (
                        external.append(request.url)
                        if not request.url.startswith(f"http://127.0.0.1:{server.server_port}/")
                        else None
                    ),
                )
                page.on("dialog", lambda dialog: dialog.accept())
                # The browser starts concurrent evidence/source fetches. Waiting
                # for global networkidle conflates page navigation with live data
                # readiness and can hang while the snapshot API is still loading.
                # Assert the actual user-facing data instead of idle transport.
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/",
                    wait_until="domcontentloaded",
                )
                sync_api.expect(page.locator("#asset-select")).to_have_value(
                    phase.run.asset_id, timeout=30000
                )
                sync_api.expect(
                    page.get_by_role("button", name="이 근거에 사람 검토 요청")
                ).to_be_visible()
                page.get_by_role("button", name="이 근거에 사람 검토 요청").click()
                sync_api.expect(page.locator("#review-results")).to_contain_text(
                    "finding-review-" + phase.run.analysis_run_id
                )
                sync_api.expect(
                    page.get_by_role("button", name="이 근거에 사람 검토 요청")
                ).to_have_count(0)
                page.get_by_role("textbox", name="검토 메모 (물리 정비 완료 기록 아님)").fill(
                    "근거 및 측정 시점 확인"
                )
                page.get_by_role("button", name="메모 기록").click()
                sync_api.expect(page.locator("#review-results")).to_contain_text("open")
                page.get_by_role("button", name="확인됨으로 표시").click()
                sync_api.expect(page.locator("#review-results")).to_contain_text("acknowledged")
                page.get_by_role("button", name="검토 기록 종료").click()
                sync_api.expect(page.locator("#review-results")).to_contain_text("closed")
                sync_api.expect(page.get_by_role("button", name="검토 기록 종료")).to_have_count(0)
                assert not errors, errors
                assert not external, external
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
            assert not thread.is_alive()
    findings = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
    events = JsonFindingReviewRepository(workspace.maintenance_review_state_path).list_events()
    assert len(findings) == 1
    assert len(events) == 3
    assert [event.action.value for event in events] == ["note", "acknowledge", "close"]
