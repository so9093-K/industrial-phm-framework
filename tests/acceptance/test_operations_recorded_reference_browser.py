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

pytestmark = pytest.mark.linux_only


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
    review_url = ""
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                page.goto(f"http://127.0.0.1:{port}/web/#connect")
                page.get_by_text("작업공간 안 CSV · 3상 역할 지정", exact=True).click()
                form = (
                    page.get_by_role("region", name="다른 방법으로 연결")
                    .locator("details")
                    .filter(has_text="작업공간 안 CSV · 3상 역할 지정")
                )
                fields = {
                    "연결 ID": source_id,
                    "연결 이름": "AI-Hub 보일러 2297 · 2020년 기록",
                    "설비": asset_id,
                    "측정 위치 (선택)": "recorded-board-1",
                    "측정 컬럼 (쉼표로 구분)": ",".join(provenance["channels"]),
                    "시간 컬럼": "timestamp",
                }
                for label, value in fields.items():
                    form.get_by_label(label, exact=True).fill(value)
                form.get_by_label("내 컴퓨터의 CSV", exact=False).set_input_files(str(csv_path))
                roles = form.get_by_role("group", name="3상 역할 (선택 · 3상 불평형 분석에 필요)")
                for channel, quantity, phase, _unit, _interpretation in csv.reader(
                    bindings.splitlines()
                ):
                    roles.get_by_label(
                        ("전압" if quantity == "voltage" else "전류") + " " + phase + "상"
                    ).select_option(channel)
                for _index, row in enumerate(csv.reader(bindings.splitlines())):
                    # UI role order is voltage R/S/T then current R/S/T.
                    quantity, phase = row[1:3]
                    role = form.locator(".role").nth(
                        (0 if quantity == "voltage" else 3) + "RST".index(phase)
                    )
                    role.get_by_label("단위 근거").fill(row[3])
                    role.get_by_label("해석 근거").fill(row[4])
                form.get_by_role("button", name="점검 (저장 안 함)").click()
                pw.expect(form).to_contain_text("측정값 60행")
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()
                form.get_by_role("button", name="연결 등록", exact=True).click()
                card = page.get_by_role("article", name="AI-Hub 보일러 2297 · 2020년 기록")
                for step in ("이 연결 사용하기", "파일 읽기 확인", "측정 이력 저장"):
                    card.get_by_role("button", name=step, exact=True).click()
                    pw.expect(card.get_by_role("button", name=step, exact=True)).to_have_count(
                        0, timeout=60_000
                    )
                card.get_by_role("link", name="측정 신호 보기").click()
                signal = page.get_by_role("region", name="측정 신호")
                pw.expect(signal.get_by_role("heading", name="마지막 저장값")).to_be_visible()
                signal.get_by_label("신호", exact=True).select_option(provenance["channels"][0])
                signal.get_by_text("측정 의미의 근거", exact=True).click()
                pw.expect(signal).to_contain_text(provenance["archive_sha256"])
                pw.expect(signal).to_contain_text("source timezone unverified")
                signal.get_by_label("기간 기준").select_option("now")
                pw.expect(signal.get_by_role("img")).to_have_count(0)
                pw.expect(signal).to_contain_text("2020")
                signal.get_by_label("기간 기준").select_option("latest")
                pw.expect(signal.get_by_role("img").first).to_be_visible()
                page.screenshot(path=str(output / f"recorded-{width}.png"))
                page.goto(f"http://127.0.0.1:{port}/web/?page=system")
                card.get_by_text("다른 작업").click()
                card.get_by_role("button", name="3상 불평형 분석").click()
                pw.expect(card).to_contain_text("3상 불평형 분석을 저장했습니다")
                card.get_by_role("link", name="분석 기록에서 보기").click()
                record = page.get_by_role("article", name="3상 불평형 분석 · " + asset_id)
                record.get_by_role("button", name="검토 요청").click()
                record.get_by_role("link", name="정비 검토함에서 보기").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                detail.get_by_label("메모 (최대 1000자)").fill(
                    "AI-Hub 과거 기록 확인; 시간대는 Asia/Seoul 가정"
                )
                detail.get_by_role("button", name="메모 남기기").click()
                pw.expect(detail).to_contain_text("검토 기록을 남겼습니다")
                detail.get_by_role("button", name="확인함으로 표시").click()
                detail.get_by_role("button", name="검토 종료", exact=True).click()
                detail.get_by_role("button", name="종료하기").click()
                pw.expect(detail.get_by_role("button", name="메모 남기기")).to_have_count(0)
                pw.expect(detail).to_contain_text("검토 종료")
                review_url = page.url
                page.screenshot(path=str(output / f"review-{width}.png"))
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    (run,) = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).list_results()
    assert run.run.source_id == source_id and run.evidence.results[0].evaluated_samples == 60
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    events = history.query_file_events(source_id)
    assert len(events) == 180 and all(event.event_at.year == 2020 for event in events)
    assert all(event.source_sha256 == provenance["csv_sha256"] for event in events)
    source = JsonSourceRepository(workspace.source_registry_path).get(source_id)
    assert (
        isinstance(source.config, FileSourceConfig)
        and Path(source.config.source_path).read_bytes() == raw
    )
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(review_url)
                pw.expect(page.get_by_role("region", name="고른 검토 항목")).to_contain_text(
                    "AI-Hub 과거 기록 확인"
                )
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
