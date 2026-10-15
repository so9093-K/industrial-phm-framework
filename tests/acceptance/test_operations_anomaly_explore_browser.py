"""Stored measurements without a model are searched for departures from a chosen baseline."""

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


def _value(channel: str, index: int) -> float:
    wobble = (index % 5) * 0.1
    if channel == "current":
        # One clear surge at minute 150; otherwise around 10 A.
        return 10.0 + wobble + (8.0 if 150 <= index < 153 else 0.0)
    return 380.0 + wobble


@pytest.mark.parametrize("width", [390, 1280])
def test_a_surge_is_found_without_a_model_and_opens_a_comparison(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:motor:{'d' * 64}:{channel}:{index}",
                source_id="motor-file",
                asset_id="motor-01",
                channel_id=channel,
                source_file="motor.csv",
                source_sha256="d" * 64,
                source_size_bytes=10,
                sample_index=index * 2 + position,
                event_at=BASE + timedelta(minutes=index),
                value=_value(channel, index),
                source_metadata_json='{"binding":{"definition":{"unit":"%s"}}}'
                % ("A" if channel == "current" else "V"),
            )
            for position, channel in enumerate(("current", "voltage"))
            for index in range(200)
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
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=motor-01#monitor"
                )
                page.locator("#asset-capabilities").get_by_role(
                    "button", name="이상 탐지 열기"
                ).click()
                section = page.locator("#anomaly-explore")
                pw.expect(section).to_contain_text("평소 범위를 벗어난 구간 (모델 없이)")
                summary = section.locator(".anomaly-explore-summary")
                pw.expect(summary).to_contain_text("기준에서 크게 벗어난 구간 1개", timeout=30000)
                pw.expect(summary).to_contain_text("current")
                row = section.locator(".anomaly-explore-list li").first
                pw.expect(row).to_contain_text("current 위로")
                pw.expect(row).to_contain_text("18.")
                pw.expect(section.locator("circle.anomaly-explore-mark")).to_have_count(3)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

                # The departure opens a comparison of the baseline with that moment.
                row.get_by_role("button", name="구간 비교").click()
                pw.expect(page.locator(".asset-tabs a[data-tab='signals']")).to_have_attribute(
                    "aria-current", "page"
                )
                card = page.locator(".explore-series").filter(has_text="current")
                pw.expect(card.locator(".explore-lead")).to_contain_text("중앙값", timeout=30000)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
