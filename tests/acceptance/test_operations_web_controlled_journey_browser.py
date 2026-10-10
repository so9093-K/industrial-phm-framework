"""Real Chromium first-run → persisted history → review via default supervised Web."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonFindingReviewRepository,
    JsonSourceRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.runtime import (
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from tests.support.window_analysis import phase_unbalance_analysis

_RUN = "from industrial_phm.cli import main; raise SystemExit(main())"


def _cmd(*args: str) -> list[str]:
    return [sys.executable, "-c", _RUN, *args]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop(proc: subprocess.Popen[bytes], root: Path) -> None:
    if proc.poll() is not None:
        return
    subprocess.run(_cmd("operations", "stop", str(root)), capture_output=True, timeout=15)
    try:
        proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _start(root: Path, port: int, log: Path) -> subprocess.Popen[bytes]:
    with log.open("wb") as output:
        proc = subprocess.Popen(
            _cmd("operations", "start", str(root)),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    until = time.monotonic() + 55
    while time.monotonic() < until:
        if proc.poll() is not None:
            pytest.fail(f"Web exited early: {log.read_text(errors='replace')[-4000:]}")
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                conn.request("GET", "/api/v1/session", headers={"Host": f"127.0.0.1:{port}"})
                response = conn.getresponse()
                if response.status == 200:
                    response.read()
                    return proc
            finally:
                conn.close()
        except OSError:
            pass
        time.sleep(0.2)
    _stop(proc, root)
    pytest.fail("supervised Web not ready: " + log.read_text(errors="replace")[-4000:])


def _no_overflow(page, width: int) -> None:
    measured = page.evaluate("() => [window.innerWidth, document.documentElement.scrollWidth]")
    assert measured[0] == width and measured[1] <= width + 2, measured


@pytest.mark.parametrize("width", [1024, 1440])
def test_supervised_web_first_run_to_review_persists_across_restart(
    tmp_path: Path, width: int
) -> None:
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")
    workspace = OperationsWorkspace(tmp_path / "web")
    init = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(init.config, ui=OperationsUiConfig(port=port))
    )
    analysis = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    observed = datetime.now(UTC) - timedelta(minutes=3)
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        f"{observed.isoformat()},220.5,219.0,221.0\n"
        f"{(observed + timedelta(seconds=1)).isoformat()},220.7,219.2,221.1\n",
        encoding="utf-8",
    )
    log = tmp_path / "supervisor.log"
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
            errors: list[str] = []
            external: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "request",
                lambda r: (
                    external.append(r.url)
                    if not r.url.startswith(f"http://127.0.0.1:{port}/")
                    else None
                ),
            )
            page.on("dialog", lambda dialog: dialog.accept())
            try:
                page.goto(f"http://127.0.0.1:{port}/web/", wait_until="domcontentloaded")
                pw.expect(page.locator("#onboarding-state")).to_contain_text(
                    "소스 미등록", timeout=30000
                )
                handoff = page.locator("#onboarding-monitor-link")
                pw.expect(handoff).to_be_hidden()
                pw.expect(page.locator("#onboarding-next")).to_contain_text("소스를 등록하세요")
                pw.expect(page.locator("#asset-select")).to_have_value(
                    analysis.run.asset_id, timeout=30000
                )
                assert page.locator(".skip-link").get_attribute("href") == "#main"
                assert page.locator("html").get_attribute("lang") == "ko"
                guide = page.locator("#operator-reference-en")
                pw.expect(guide.locator("summary")).to_have_attribute("lang", "en")
                guide.locator("summary").click()
                pw.expect(guide.locator('div[lang="en"]')).to_contain_text("Accepted receipt:")
                pw.expect(guide.locator('div[lang="en"]')).to_contain_text(
                    "not evidence of physical maintenance"
                )
                pw.expect(page.get_by_role("heading", name="화면 상태 해석 기준")).to_be_visible()
                pw.expect(page.locator("#operator-meaning")).to_contain_text(
                    "최근 데이터 수신은 설비 정상·고장 진단이 아닙니다"
                )
                pw.expect(page.locator("#operator-meaning")).to_contain_text(
                    "검토 기록 종료도 실제 정비 완료"
                )
                assert page.locator("#last-values .latest-item").count() == 0
                page.get_by_role("link", name="데이터 연결").click()
                pw.expect(page.locator('nav a[href="#connect"]')).to_have_attribute(
                    "aria-current", "page"
                )
                fields = {
                    "source_id": "journey-file",
                    "name": "브라우저 여정",
                    "asset_id": analysis.run.asset_id,
                    "measurement_point_id": "panel",
                    "file_path": "inputs/phase.csv",
                    "channel_columns": "phase-R,phase-S,phase-T",
                    "timestamp_column": "timestamp",
                }
                for key, value in fields.items():
                    page.locator(f'#file-form input[name="{key}"]').fill(value)
                page.get_by_role("button", name="CSV 확인 후 소스 등록").click()
                listing = page.locator("#source-list")
                pw.expect(listing).to_contain_text("journey-file", timeout=30000)
                pw.expect(listing).to_contain_text("수신 근거 미확인")
                pw.expect(listing.locator(".source-meaning")).to_contain_text(
                    "소스 등록 정보만 확인"
                )
                pw.expect(page.locator("#onboarding-steps")).to_contain_text(
                    "관리 상태 active: 0개"
                )
                pw.expect(handoff).to_be_hidden()
                assert not workspace.history_catalog_path.exists()
                listing.get_by_role("button", name="소스 활성화").click()
                pw.expect(listing).to_contain_text("관리 상태: active")
                pw.expect(page.locator("#onboarding-steps")).to_contain_text(
                    "관리 상태 active: 1개"
                )
                pw.expect(page.locator("#onboarding-next")).to_contain_text(
                    "실제 검증 수신 근거를 확인하세요"
                )
                pw.expect(handoff).to_be_hidden()
                listing.get_by_role("button", name="FILE 수신 확인").click()
                pw.expect(listing).to_contain_text("FILE 검증 수신 근거 있음")
                pw.expect(listing.locator(".source-meaning")).to_contain_text(
                    "이력 저장·연속 수집·분석 성공 여부는 별도 확인"
                )
                pw.expect(page.locator("#onboarding-steps")).to_contain_text(
                    "active와 수신을 모두 확인한 소스 1개"
                )
                pw.expect(page.locator("#onboarding-next")).to_contain_text(
                    "이력 저장·분석·설비 정상 판정은 보증하지 않습니다"
                )
                pw.expect(handoff).to_be_visible()
                assert not workspace.history_catalog_path.exists()
                handoff.click()
                pw.expect(page.locator('nav a[href="#monitor"]')).to_have_attribute(
                    "aria-current", "page"
                )
                listing.get_by_role("button", name="FILE 이력 적재").click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "6개 이벤트", timeout=30000
                )
                pw.expect(page.locator("#last-values")).to_contain_text("220.7", timeout=30000)
                assert workspace.history_catalog_path.exists()
                page.get_by_role("link", name="분석 근거").click()
                pw.expect(page.locator("#evidence-results")).to_contain_text(
                    analysis.evidence.evidence_id
                )
                page.get_by_role("button", name="이 근거에 사람 검토 요청").click()
                pw.expect(page.locator("#review-results")).to_contain_text(
                    analysis.run.analysis_run_id, timeout=30000
                )
                page.get_by_role("textbox", name="검토 메모 (물리 정비 완료 기록 아님)").fill(
                    "증거 확인"
                )
                page.get_by_role("button", name="메모 기록").click()
                page.get_by_role("button", name="확인됨으로 표시").click()
                pw.expect(page.locator("#review-results")).to_contain_text("acknowledged")
                page.get_by_role("button", name="검토 기록 종료").click()
                pw.expect(page.locator("#review-results")).to_contain_text("closed")
                pw.expect(page.locator("#review-results .review-meaning")).to_contain_text(
                    "검토 기록 종료됨 · 실제 정비 완료, "
                    "고장 해결 또는 설비 안전 확인의 근거가 아닙니다"
                )
                # A closed review still links only to the exact persisted Run/Evidence.
                evidence_link = page.locator("#review-results").get_by_role(
                    "button",
                    name=f"연결된 분석 근거 확인 · {analysis.evidence.evidence_id}",
                )
                evidence_link.click()
                target = page.locator("#evidence-results .evidence-target")
                pw.expect(target).to_be_focused()
                pw.expect(target).to_contain_text(analysis.run.analysis_run_id)
                pw.expect(target).to_contain_text(analysis.evidence.evidence_id)
                pw.expect(page.locator('nav a[href="#evidence"]')).to_have_attribute(
                    "aria-current", "page"
                )
                _no_overflow(page, width)
                assert not errors, errors
                assert not external, external
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    assert JsonSourceRepository(workspace.source_registry_path).get("journey-file")
    repository = JsonFindingReviewRepository(workspace.maintenance_review_state_path)
    assert [event.action.value for event in repository.list_events()] == [
        "note",
        "acknowledge",
        "close",
    ]

    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/web/", wait_until="domcontentloaded")
                pw.expect(page.locator("#review-results")).to_contain_text("closed", timeout=30000)
                pw.expect(page.locator("#review-results .review-meaning")).to_contain_text(
                    "실제 정비 완료, 고장 해결 또는 설비 안전 확인의 근거가 아닙니다"
                )
                pw.expect(page.locator("#last-values")).to_contain_text("220.7", timeout=30000)
                handoff = page.locator("#onboarding-monitor-link")
                pw.expect(handoff).to_be_visible()
                # Losing the real source GET must revoke a prior ready state,
                # without claiming the stored measurements or review disappeared.
                page.route("**/api/v1/sources", lambda route: route.abort("failed"))
                page.get_by_role("button", name="데이터 다시 불러오기").click()
                pw.expect(page.locator("#onboarding-next")).to_contain_text(
                    "준비 여부를 확인할 수 없습니다"
                )
                pw.expect(handoff).to_be_hidden()
                page.unroute("**/api/v1/sources")
                page.get_by_role("button", name="데이터 다시 불러오기").click()
                pw.expect(handoff).to_be_visible()
                pw.expect(page.locator("#onboarding-steps")).to_contain_text(
                    "active와 수신을 모두 확인한 소스 1개"
                )
                pw.expect(
                    page.get_by_role("button", name="이 근거에 사람 검토 요청")
                ).to_have_count(0)
                pw.expect(page.get_by_role("button", name="검토 기록 종료")).to_have_count(0)
                page.locator("#review-results").get_by_role(
                    "button",
                    name=f"연결된 분석 근거 확인 · {analysis.evidence.evidence_id}",
                ).click()
                target = page.locator("#evidence-results .evidence-target")
                pw.expect(target).to_be_focused()
                pw.expect(target).to_contain_text(analysis.run.analysis_run_id)
                pw.expect(target).to_contain_text(analysis.evidence.evidence_id)
                _no_overflow(page, width)
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    assert len(repository.list_events()) == 3
