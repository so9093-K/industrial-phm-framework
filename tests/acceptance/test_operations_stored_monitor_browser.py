"""The default Monitor observes stored equipment signals without any connected PHM model."""

from __future__ import annotations

import math
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

ASSET = "motor-07"
T0 = datetime(2020, 3, 2, tzinfo=UTC)


def _record(
    root: Path, history: DuckLakeAssetHistory, source_id: str, rows: list[tuple[int, float]]
) -> None:
    """Persist recorded history whose source is not registered in the workspace."""
    path = root / f"{source_id}.csv"
    path.write_text(
        "timestamp,current_r,current_s\n"
        + "".join(f"{(T0 + timedelta(seconds=s)).isoformat()},{v},{v + 1}\n" for s, v in rows),
        encoding="utf-8",
    )
    registry = JsonSourceRepository(root / f"{source_id}-registry.json")
    registry.register(
        RegisteredSource(
            source_id=source_id,
            name=source_id,
            config=FileSourceConfig(
                str(path),
                ASSET,
                channel_columns=("current_r", "current_s"),
                timestamp_column="timestamp",
            ),
            registered_at=T0,
        )
    )
    backfill_registered_file_source(registry, history, source_id)


@pytest.mark.parametrize("width", [390, 1440])
def test_model_less_asset_shows_stored_signal_and_follows_new_history(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    # 00:00-00:59 UTC every 10 s with a real 10 minute gap; the last value is at 00:59:50.
    first = [(s, round(10 + math.sin(s / 300), 3)) for s in range(0, 3600, 10)]
    _record(tmp_path, history, "recorder-a", [r for r in first if not 1800 <= r[0] < 2400])
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                trends: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "request",
                    lambda r: trends.append(r.url) if "channel_id=current_" in r.url else None,
                )
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#monitor")
                asset = page.locator(f'.monitor-asset[data-asset-id="{ASSET}"]')
                pw.expect(asset).to_contain_text("저장된 과거 기록", timeout=15_000)
                pw.expect(asset).to_contain_text("PHM 분석 연결 안 됨")
                pw.expect(page.locator("#monitor-signal-mode")).to_have_text("저장 측정 이력")
                pw.expect(page.locator("#monitor-detection-results")).to_contain_text(
                    "연결된 PHM 분석 모델 없음"
                )
                reading = page.locator("#monitor-signal-reading")
                # The original 00:59:50 UTC record is shown as KST and is not called a receipt.
                pw.expect(reading).to_contain_text("원본 측정 2020-03-02 09:59:50 KST")
                pw.expect(reading).to_contain_text(f"{first[-1][1]:g}")
                pw.expect(reading).to_contain_text("단위 미확인")
                line = page.locator("#monitor-signal-chart .monitor-raw-line")
                pw.expect(line).to_have_count(1)
                # The stored gap stays a gap: two separate segments, never one joined line.
                assert line.get_attribute("d").count("M") == 2
                page.locator("#monitor-signal-channel").select_option("current_s")
                pw.expect(reading).to_contain_text(f"{first[-1][1] + 1:g}")

                # New stored history arrives; no manual refresh, selection is retained.
                later = [(3600 + s, 20.5 + s / 100) for s in range(0, 600, 10)]
                _record(tmp_path, history, "recorder-b", later)
                pw.expect(reading).to_contain_text(
                    "원본 측정 2020-03-02 10:09:50 KST", timeout=15_000
                )
                pw.expect(reading).to_contain_text("recorder-b")
                pw.expect(page.locator("#monitor-signal-channel")).to_have_value("current_s")
                # Two sources are separate series, not merged into one line.
                pw.expect(
                    page.locator("#monitor-signal-chart .monitor-stored-source")
                ).to_have_count(2)

                # Without new data the stored trend is not re-read on every 3 second poll.
                settled = len(trends)
                page.wait_for_timeout(9_000)
                assert len(trends) - settled <= 1, trends[settled:]

                # A failed history read never leaves an earlier value on screen.
                page.route("**/api/v1/history/trend?**", lambda r: r.fulfill(status=503, json={}))
                page.get_by_role("button", name="데이터 다시 불러오기").click()
                pw.expect(page.locator("#monitor-signal-state")).to_contain_text(
                    "읽지 못했습니다", timeout=10_000
                )
                pw.expect(reading).to_be_hidden()
                pw.expect(line).to_have_count(0)
                page.unroute("**/api/v1/history/trend?**")
                pw.expect(reading).to_contain_text("recorder-b", timeout=15_000)

                # A PHM read failure does not hide model-independent observation.
                page.route("**/api/v1/phm/monitor", lambda r: r.fulfill(status=503, json={}))
                pw.expect(page.locator("#phm-monitor-state")).to_contain_text(
                    "PHM 조회 실패", timeout=10_000
                )
                pw.expect(asset).to_contain_text("PHM 분석 조회 실패")
                pw.expect(page.locator("#monitor-signal-chart svg").first).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
