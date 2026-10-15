"""Delivered waveforms that no model reads yet still list their asset and lead to a model."""

from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_monitor
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace


def test_the_monitor_read_names_streams_no_model_reads(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    (stream,) = project_phm_monitor(store, workspace.models_path, snapshots)["unbound_streams"]
    assert (stream["asset_id"], stream["source_id"], stream["last_ordinal"]) == (
        "bearing-a",
        "bench",
        3,
    )
    assert stream["recorded_replay"] is True

    bound = phm_workspace(tmp_path / "bound")
    deliver(bound, tmp_path / "waves-b", 1, 0.5)
    analyze(bound)
    read = project_phm_monitor(
        SqlitePhmAnalysisStore(bound.phm_analysis_path),
        bound.models_path,
        SqliteAcquisitionSnapshotRepository(bound.acquisition_snapshot_path),
    )
    assert read["unbound_streams"] == []


@pytest.mark.parametrize("width", [390, 1280])
def test_waveforms_without_a_model_are_listed_and_lead_to_one(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
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
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#monitor")
                # Stored waveforms are data: no empty-workspace start screen.
                card = page.locator('.monitor-asset[data-asset-id="bearing-a"]')
                pw.expect(card).to_contain_text("분석 · 모델 연결 전", timeout=30000)
                pw.expect(card).to_contain_text("진동 파형 #3까지 저장")
                pw.expect(page.locator("#workspace-start")).to_be_hidden()
                pw.expect(page.locator("#asset-switch")).to_have_value("bearing-a")
                pw.expect(page.locator("#monitor-signal-state")).to_contain_text(
                    "이상 탐지 모델이 아직 없습니다"
                )
                anomaly = page.locator('#asset-capabilities [data-capability="anomaly"]')
                pw.expect(anomaly).to_contain_text("입력이 맞는 모델 2개")
                page.locator("#monitor-detection-results").get_by_role(
                    "button", name="이상 탐지 모델 연결"
                ).click()
                pw.expect(page.locator("#anomaly-connect")).to_contain_text(
                    "연결할 수 있는 이상 탐지 모델"
                )
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
