"""The forecast tab continues a stored signal, reaches a management level, and checks itself."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import phm_workspace

BASE = datetime(2026, 10, 14, tzinfo=UTC)


@pytest.mark.parametrize("width", [390, 1280])
def test_a_stored_signal_is_forecast_with_its_level_and_its_own_check(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:motor:{'c' * 64}:{index}",
                source_id="motor-file",
                asset_id="motor-01",
                channel_id="current",
                source_file="motor.csv",
                source_sha256="c" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + 0.02 * index,
                source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
            )
            for index in range(180)
        ),
        batch_id="motor",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=motor-01"
                # From the overview's shortcuts straight to the forecast of the same asset.
                page.goto(base + "#monitor")
                page.locator("#asset-capabilities").get_by_role(
                    "button", name="미래 예측 열기"
                ).click()
                panel = page.locator("#forecast")
                pw.expect(panel.locator(".forecast-chart")).to_be_visible(timeout=30000)
                summary = panel.locator(".forecast-summary")
                pw.expect(summary).to_contain_text("증가 · 마지막 측정")
                pw.expect(summary).to_contain_text("1시간 뒤")
                pw.expect(summary).to_contain_text("과거 자료로 확인")
                pw.expect(panel.get_by_role("button", name="24시간")).to_be_disabled()
                pw.expect(panel.get_by_role("button", name="1시간")).to_have_attribute(
                    "aria-pressed", "true"
                )

                panel.get_by_label("관리 기준 (선택)").fill("14.3")
                panel.get_by_role("button", name="기준 적용").click()
                pw.expect(summary).to_contain_text("관리 기준 14.3 A")
                pw.expect(summary).to_contain_text("예상 도달")
                pw.expect(panel.locator("line.forecast-threshold")).to_have_count(1)
                assert "forecast_threshold=14.3" in page.url
                page.reload()
                pw.expect(summary).to_contain_text("관리 기준 14.3 A", timeout=30000)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

                # An old remaining-life link opens its replacement.
                page.goto(base + "#rul")
                pw.expect(page.locator(".asset-tabs a[data-tab='forecast']")).to_have_attribute(
                    "aria-current", "page"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
