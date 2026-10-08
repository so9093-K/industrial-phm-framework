"""Chromium acceptance for the opt-in, real-data read-only Web monitor.

This does not launch or switch the supervised marimo Operations product.
A real FILE→DuckLake ingestion is queried through the same local HTTP routes
that the packaged browser JS fetches. No mocked API, diagnostic or live claim.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    RegisteredSource,
    backfill_registered_file_source,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


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
            page.locator('input[name="source_id"]').fill("web-file-01")
            page.locator('input[name="name"]').fill("웹 등록 CSV")
            page.locator('input[name="asset_id"]').fill("pump-01")
            page.locator('input[name="measurement_point_id"]').fill("panel")
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
            page.locator('input[name="source_id"]').fill("file-receipt")
            page.locator('input[name="name"]').fill("FILE receipt")
            page.locator('input[name="asset_id"]').fill("pump-01")
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
