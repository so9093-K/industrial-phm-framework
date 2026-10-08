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
