"""Opt-in real AI-Hub recording journey; external data is never downloaded by tests."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from tests.acceptance.test_operations_web_controlled_journey_browser import _port, _start, _stop


@pytest.mark.parametrize("width", [1024, 1440])
def test_recorded_reference_observation_analysis_review_and_restart(
    tmp_path: Path, width: int
) -> None:
    configured = os.environ.get("PHM_RECORDED_REFERENCE")
    if not configured:
        pytest.skip("opt-in local recorded data: set PHM_RECORDED_REFERENCE")
    pw = pytest.importorskip("playwright.sync_api")
    reference = Path(configured).resolve()
    provenance = json.loads((reference / "provenance.json").read_text(encoding="utf-8"))
    csv_path = reference / "recorded-phase.csv"
    raw = csv_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == provenance["csv_sha256"]
    bindings = (reference / "phase-bindings.txt").read_text(encoding="utf-8")
    with csv_path.open(encoding="utf-8", newline="") as stream:
        recorded = list(csv.DictReader(stream))
    assert len(recorded) == provenance["row_count"] == 60
    assert all(row["source_timestamp_local"].startswith("2020-11-13") for row in recorded)
    output = Path(os.environ.get("PHM_RECORDED_EVIDENCE", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    workspace = OperationsWorkspace(output / f"workspace-{width}")
    assert not workspace.root.exists(), "use a new evidence directory for each recorded run"
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    log = output / f"supervisor-{width}.log"
    source_id = "aihub239-recorded-boiler-2297"
    asset_id = "research-boiler-2297"
    proc = _start(workspace.root, port, log)
    analysis_id = evidence_id = ""
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())
                page.goto(f"http://127.0.0.1:{port}/web/", wait_until="networkidle")
                pw.expect(page.locator("#workspace-state")).to_have_text("빈 작업공간")
                page.screenshot(path=str(output / f"empty-{width}.png"))
                page.get_by_role("link", name="기존 연구 결과 보기").click()
                pw.expect(page.locator("#research-state")).to_contain_text("11건")
                result = page.locator(".research-result").filter(
                    has_text="xjtu-sy-lstm-autoencoder-fold-1-development-v1"
                )
                result.locator("summary").click()
                pw.expect(result).to_contain_text("원본 데이터")
                assert page.locator("#analysis-count").inner_text() == "0"
                page.locator('nav a[href="#connect"]').click()
                fields = {
                    "source_id": source_id,
                    "name": "AI-Hub 보일러 2297 · 2020년 기록",
                    "asset_id": asset_id,
                    "measurement_point_id": "recorded-board-1",
                    "channel_columns": ",".join(provenance["channels"]),
                    "timestamp_column": "timestamp",
                }
                for name, value in fields.items():
                    page.locator(f'#file-form input[name="{name}"]').fill(value)
                page.locator("#csv-upload").set_input_files(str(csv_path))
                page.locator('#file-form textarea[name="phase_bindings"]').fill(bindings)
                page.get_by_role("button", name="CSV 분석 전 점검", exact=True).click()
                pw.expect(page.locator("#csv-preflight-result")).to_contain_text("표본 60행")
                assert not workspace.source_registry_path.exists()
                page.get_by_role("button", name="CSV 확인 후 소스 등록", exact=True).click()
                card = page.locator(f'.source-record[data-source-id="{source_id}"]')
                pw.expect(card).to_contain_text("수신 근거 미확인")
                assert not workspace.history_catalog_path.exists()
                card.get_by_role("button", name="소스 활성화", exact=True).click()
                pw.expect(card).to_contain_text("관리 상태: active")
                card.get_by_role("button", name="FILE 수신 확인", exact=True).click()
                pw.expect(card).to_contain_text("FILE 검증 수신 근거 확인")
                assert not workspace.history_catalog_path.exists()
                card.get_by_role("button", name="FILE 이력 적재", exact=True).click()
                pw.expect(page.locator("#source-control-result")).to_contain_text("180개 이벤트")
                page.locator('nav a[href="#monitor"]').click()
                pw.expect(page.locator("#workspace-state")).to_have_text("저장된 기록 데이터")
                pw.expect(page.locator("#first-run")).to_be_hidden()
                pw.expect(page.locator("#last-values")).to_contain_text("2020-11-12T15:59:04Z")
                page.locator('nav a[href="#signals"]').click()
                pw.expect(page.locator("#trend-results .trend-dot").first).to_be_visible()
                first = page.locator("#trend-results .trend-group").first
                first.locator("summary").click()
                pw.expect(first).to_contain_text(provenance["archive_sha256"])
                pw.expect(first).to_contain_text("source timezone unverified")
                page.locator('#channel-options input[value="S상전압"]').check()
                page.locator("#show-trend").click()
                pw.expect(page.locator("#last-values .latest-item")).to_have_count(2)
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(output / f"recorded-{width}.png"))
                box = page.locator("#last-values").bounding_box()
                # Observation controls and latest values precede the recorded graph.
                action = page.locator("#show-trend").bounding_box()
                assert action and action["y"] + action["height"] <= 900
                assert box is not None
                first_value = page.locator("#last-values .latest-item").first.bounding_box()
                assert first_value and first_value["y"] + first_value["height"] <= 900
                page.locator('nav a[href="#research"]').click()
                page.go_back(wait_until="networkidle")
                pw.expect(page.locator('#channel-options input[value="S상전압"]')).to_be_checked()
                page.locator("#refresh").click()
                pw.expect(page.locator("#last-values .latest-item")).to_have_count(2)
                pw.expect(page.locator('#channel-options input[value="S상전압"]')).to_be_checked()
                # 'now' stays distinct and cannot silently move old records into the present.
                page.locator("#time-anchor").select_option("now")
                pw.expect(page.locator("#trend-results .trend-dot")).to_have_count(0)
                pw.expect(page.locator("#last-values")).to_contain_text("2020-11-12")
                page.locator("#time-anchor").select_option("latest")
                pw.expect(page.locator("#trend-results .trend-dot").first).to_be_visible()
                page.locator('nav a[href="#connect"]').click()
                card.get_by_role("button", name="저장된 3상 이력 분석 실행", exact=True).click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "신규 3상 분석 기록 완료"
                )
                runs = SqlitePhaseUnbalanceRepository(
                    workspace.phase_unbalance_state_path
                ).list_results()
                assert len(runs) == 1
                run = runs[0]
                analysis_id, evidence_id = run.run.analysis_run_id, run.evidence.evidence_id
                assert run.run.source_id == source_id
                assert run.evidence.results[0].evaluated_samples == 60
                pw.expect(page.locator("#evidence-results")).to_contain_text(evidence_id)
                page.get_by_role("button", name="이 근거에 사람 검토 요청", exact=True).click()
                pw.expect(page.locator("#review-results")).to_contain_text(analysis_id)
                page.get_by_role("textbox", name="검토 메모 (물리 정비 완료 기록 아님)").fill(
                    "AI-Hub 과거 기록 확인; 시간대는 Asia/Seoul 가정; 현장 고장 판정 없음"
                )
                page.get_by_role("button", name="메모 기록", exact=True).click()
                page.get_by_role("button", name="확인됨으로 표시", exact=True).click()
                pw.expect(page.locator("#review-results")).to_contain_text("acknowledged")
                page.get_by_role("button", name="검토 기록 종료", exact=True).click()
                pw.expect(page.locator("#review-results")).to_contain_text("closed")
                page.screenshot(path=str(output / f"review-{width}.png"))
                assert not errors, errors
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    events = history.query_file_events(source_id)
    assert len(events) == 180
    assert all(event.event_at.year == 2020 for event in events)
    assert all(event.source_sha256 == provenance["csv_sha256"] for event in events)
    source = JsonSourceRepository(workspace.source_registry_path).get(source_id)
    assert isinstance(source.config, FileSourceConfig)
    assert Path(source.config.source_path).read_bytes() == raw
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/web/#review", wait_until="networkidle")
                pw.expect(page.locator("#review-results")).to_contain_text(analysis_id)
                pw.expect(page.locator("#review-results")).to_contain_text("closed")
                page.get_by_role(
                    "button", name="연결된 분석 근거 확인" + " · " + evidence_id, exact=True
                ).click()
                pw.expect(page.locator("#evidence-results")).to_be_visible()
                pw.expect(page.locator("#evidence-results .evidence-target")).to_be_focused()
                page.screenshot(path=str(output / f"restart-{width}.png"))
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    (output / f"journey-{width}.json").write_text(
        json.dumps(
            {
                "workspace": str(workspace.root.resolve()),
                "source_id": source_id,
                "archive_sha256": provenance["archive_sha256"],
                "csv_sha256": provenance["csv_sha256"],
                "analysis_run_id": analysis_id,
                "evidence_id": evidence_id,
                "historical_event_count": len(events),
                "restart_verified": True,
                "browser_width": width,
                "human_usability_review": "pending",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
