"""From an asset's overview, what its data supports opens the first result with the asset kept."""

# The screen writes acquisition ranges with an en dash between the numbers.
# ruff: noqa: RUF001

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace

BASE = datetime(2026, 10, 14, tzinfo=UTC)


class _InProcessSupervisor:
    """Executes authorized actions the way the supervisor broker does, without IPC."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        return execute_web_source_action(self.root, route, payload)


@pytest.mark.parametrize("width", [390, 1280])
def test_the_overview_says_what_each_assets_data_supports_and_opens_it(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:motor:{'e' * 64}:{channel}:{index}",
                source_id="motor-file",
                asset_id="motor-01",
                channel_id=channel,
                source_file="motor.csv",
                source_sha256="e" * 64,
                source_size_bytes=10,
                sample_index=index * 2 + position,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + index * (position + 1),
            )
            for position, channel in enumerate(("current", "temperature"))
            for index in range(40)
        ),
        batch_id="motor",
    )
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
                base = f"http://127.0.0.1:{server.server_port}/web/"
                page.goto(base + "?monitor_asset=motor-01#monitor")
                listing = page.locator("#asset-capabilities")
                pw.expect(listing.locator("h3")).to_have_text("분석 바로가기")
                # Operations runs behind this page: no view-only notice.
                pw.expect(page.locator(".view-only-context")).to_have_count(0)
                pw.expect(listing.locator(".capability")).to_have_count(4)
                pw.expect(listing.locator('[data-capability="anomaly"]')).to_contain_text(
                    "모델 없이 기준 구간에서 벗어난 값 찾기"
                )
                pw.expect(listing.locator('[data-capability="measurements"]')).to_contain_text(
                    "신호 2개 ·"
                )
                # What this data cannot support stays one quiet line, each with its reason.
                unavailable = listing.locator(".capability-unavailable")
                pw.expect(unavailable).to_contain_text("주파수 성분 — 원본 진동 파형 없음")
                pw.expect(unavailable).to_contain_text("AI 질문 — 모델 결과 없음")
                pw.expect(unavailable).to_contain_text("상태 전망 — 기록이 짧음")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

                # Ready analyses open their first result for the same asset.
                listing.get_by_role("button", name="구간 비교 열기").click()
                pw.expect(page.locator("#explore-state")).to_contain_text("측정 이력 · 구간 A")
                pw.expect(page.locator(".explore-series").first).to_be_visible()
                pw.expect(page.locator("#asset-switch")).to_have_value("motor-01")

                page.locator('.asset-tabs a[data-tab="monitor"]').click()
                listing.get_by_role("button", name="신호 관계 열기").click()
                pw.expect(page.locator(".explore-relation table")).to_contain_text("구간 A")

                # Vibration with connected models: every analysis, and the question form.
                page.locator("#asset-switch").select_option("bearing-a")
                page.locator('.asset-tabs a[data-tab="monitor"]').click()
                # Every analysis opens; the waveform itself is already on the overview above.
                pw.expect(listing.locator(".capability")).to_have_count(5)
                pw.expect(listing.locator(".capability-unavailable")).to_have_text(
                    "사용 불가상태 전망 — 기록이 짧음 (예측 기간의 2배 이상 필요)"
                )
                pw.expect(listing.locator('[data-capability="period-compare"]')).to_contain_text(
                    "획득 #1–#8"
                )
                listing.get_by_role("button", name="주파수 성분 열기").click()
                pw.expect(page.locator("svg.explore-spectrum-chart")).to_be_visible()
                page.locator('.asset-tabs a[data-tab="monitor"]').click()
                listing.get_by_role("button", name="AI 질문 열기").click()
                pw.expect(page.locator(".asset-tabs a[data-tab='anomaly']")).to_have_attribute(
                    "aria-current", "page"
                )
                pw.expect(page.locator("#anomaly-assistant textarea")).to_be_focused()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_a_fitting_model_that_is_not_connected_yet_is_one_click_away(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    # The bearing also has a stored temperature record, so it is listed before any model.
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:bearing:{'a' * 64}:{index}",
                source_id="bearing-file",
                asset_id="bearing-a",
                channel_id="temperature",
                source_file="bearing.csv",
                source_sha256="a" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=40.0 + index,
            )
            for index in range(10)
        ),
        batch_id="bearing",
    )
    root = workspace.root.resolve()
    server = create_operations_web_read_server(root, command_client=_InProcessSupervisor(root))  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a#monitor"
                )
                anomaly = page.locator('#asset-capabilities [data-capability="anomaly"]')
                pw.expect(anomaly).to_contain_text("맞는 모델 2개 연결 가능")
                anomaly.get_by_role("button", name="이상 탐지 열기").click()
                pw.expect(page.locator("#anomaly-explore")).to_contain_text(
                    "평소 범위를 벗어난 구간"
                )
                connect = page.locator("#anomaly-connect")
                pw.expect(connect).to_contain_text("연결할 수 있는 이상 탐지 모델")
                pw.expect(connect).to_contain_text("synthetic-vertical-score-v1")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
