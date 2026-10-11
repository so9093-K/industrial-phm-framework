"""Real Chromium CSV → fresh analysis → exact review → restart via supervised Web."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonFileFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonSourceRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.runtime import (
    OperationsComponentKind,
    OperationsSupervisorStateKind,
    OperationsSupervisorStateRepository,
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from industrial_phm.runtime.operations_web_actions import (
    WEB_SOURCE_ACTION_ROUTES,
    WEB_SUPERVISOR_ONLY_ACTION_ROUTES,
)

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
    asset_id = "journey-pump"
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    observed = datetime.now(UTC) - timedelta(minutes=3)
    (inputs / "vibration.csv").write_text(
        "timestamp,vibration_x,vibration_y\n"
        f"{observed.isoformat()},-1.0,2.0\n"
        f"{(observed + timedelta(seconds=1)).isoformat()},0.0,3.0\n"
        f"{(observed + timedelta(seconds=2)).isoformat()},1.5,4.0\n",
        encoding="utf-8",
    )
    (inputs / "phase.csv").write_text(
        "timestamp,leg_a,leg_b,leg_c\n"
        f"{observed.isoformat()},220.0,225.0,230.0\n"
        f"{(observed + timedelta(seconds=1)).isoformat()},222.0,226.0,231.0\n"
        f"{(observed + timedelta(seconds=2)).isoformat()},221.0,224.0,228.0\n",
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
                pw.expect(page.locator("#runtime-facts")).to_contain_text(
                    str(proc.pid), timeout=30000
                )
                pw.expect(page.locator("#runtime-components")).to_contain_text("데이터 수집기")
                pw.expect(page.locator("#runtime-components")).to_contain_text("분석 실행기")
                pw.expect(page.locator("#runtime-components")).to_contain_text("Web 화면")
                page.get_by_role("button", name="실행 상태 다시 확인").click()
                pw.expect(page.locator("#runtime-facts")).to_contain_text(str(proc.pid))
                pw.expect(page.locator("#onboarding-state")).to_contain_text(
                    "소스 미등록", timeout=30000
                )
                handoff = page.locator("#onboarding-monitor-link")
                pw.expect(handoff).to_be_hidden()
                pw.expect(page.locator("#onboarding-next")).to_contain_text("소스를 등록하세요")
                page.get_by_role("button", name="CSV 등록 양식으로 이동").click()
                pw.expect(page.locator('#file-form input[name="source_id"]')).to_be_focused()
                pw.expect(page.locator('nav a[href="#connect"]')).to_have_attribute(
                    "aria-current", "page"
                )
                pw.expect(page.locator("#asset-select")).to_be_disabled()
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
                    "asset_id": asset_id,
                    "measurement_point_id": "panel",
                    "channel_columns": "vibration_x,vibration_y",
                    "timestamp_column": "timestamp",
                }
                for key, value in fields.items():
                    page.locator(f'#file-form input[name="{key}"]').fill(value)
                page.locator("#csv-upload").set_input_files(
                    {
                        "name": "vibration.csv",
                        "mimeType": "text/csv",
                        "buffer": (inputs / "vibration.csv").read_bytes(),
                    }
                )
                pw.expect(page.locator("#csv-file-preview")).to_contain_text(
                    "헤더 후보: timestamp, vibration_x, vibration_y"
                )
                pw.expect(page.locator('#file-form input[name="file_path"]')).to_be_disabled()
                page.get_by_role("button", name="CSV 분석 전 점검").click()
                pw.expect(page.locator("#csv-preflight-result")).to_contain_text(
                    "CSV 구조와 이력 적재의 필수 조건 확인", timeout=30000
                )
                pw.expect(page.locator("#csv-preflight-result")).to_contain_text(
                    "표본 3행"
                )
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()
                assert not (workspace.root / "web-uploads").exists()
                assert not workspace.history_catalog_path.exists()
                page.get_by_role("button", name="CSV 확인 후 소스 등록").click()
                listing = page.locator("#source-list")
                pw.expect(listing).to_contain_text("journey-file", timeout=30000)
                pw.expect(page.locator("#asset-select")).to_have_value(asset_id)
                saved_uploads = tuple((workspace.root / "web-uploads").glob("*.csv"))
                assert len(saved_uploads) == 1
                assert saved_uploads[0].read_bytes() == (inputs / "vibration.csv").read_bytes()
                pw.expect(listing).to_contain_text("수신 근거 미확인")
                pw.expect(listing.locator(".source-meaning")).to_contain_text(
                    "소스 등록 정보만 확인"
                )
                pw.expect(page.locator("#onboarding-steps")).to_contain_text(
                    "관리 상태 active: 0개"
                )
                pw.expect(page.locator("#onboarding-source-select")).to_have_value("journey-file")
                page.get_by_role("button", name="소스 활성화 버튼 찾기").click()
                pw.expect(listing.get_by_role("button", name="소스 활성화")).to_be_focused()
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
                page.get_by_role("button", name="FILE 수신 확인 버튼 찾기").click()
                pw.expect(listing.get_by_role("button", name="FILE 수신 확인")).to_be_focused()
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
                page.get_by_role("button", name="FILE 이력 적재 버튼 찾기").click()
                pw.expect(listing.get_by_role("button", name="FILE 이력 적재")).to_be_focused()
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
                pw.expect(page.locator("#last-values")).to_contain_text("1.5", timeout=30000)
                assert workspace.history_catalog_path.exists()
                listing.get_by_role("button", name="CSV 특징 분석 실행").click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "신규 분석 근거 저장 완료", timeout=30000
                )
                analyses = JsonFileFeatureAnalysisRepository(
                    workspace.file_feature_analysis_path
                ).list_results()
                assert len(analyses) == 1
                analysis = analyses[0]
                assert analysis.run.source_id == "journey-file"
                assert analysis.run.asset_id == asset_id
                assert (
                    analysis.evidence.source_snapshot_sha256
                    == hashlib.sha256((inputs / "vibration.csv").read_bytes()).hexdigest()
                )
                page.get_by_role("link", name="분석 근거").click()
                pw.expect(page.locator("#evidence-results")).to_contain_text(
                    analysis.evidence.evidence_id
                )
                page.get_by_role("button", name="이 근거에 사람 검토 요청").click()
                pw.expect(page.locator("#review-results")).to_contain_text(
                    analysis.run.analysis_run_id, timeout=30000
                )
                pw.expect(page.locator("#review-inbox-summary")).to_contain_text("미처리 1건")
                page.locator("#review-inbox-list button").first.click()
                pw.expect(page.locator("#review-results .review-record")).to_be_focused()
                page.get_by_role("link", name="분석 근거").click()
                page.get_by_role("button", name="이 분석의 검토 기록 열기").click()
                pw.expect(page.locator("#review-results .review-record")).to_be_focused()
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
                pw.expect(page.locator("#review-inbox-summary")).to_contain_text("미처리 0건")
                pw.expect(page.locator("#review-inbox-list")).to_contain_text(
                    "표시 조건에 맞는 검토 기록이 없습니다"
                )
                page.locator("#review-filter").select_option("closed")
                pw.expect(page.locator("#review-inbox-list")).to_contain_text(
                    analysis.run.analysis_run_id
                )
                page.locator("#review-inbox-list button").first.click()
                pw.expect(page.locator("#review-results .review-record")).to_be_focused()
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
                # A distinct CSV with deliberately non-phase column names
                # requires explicit evidence-backed V/A and R/S/T mapping.
                page.get_by_role("link", name="데이터 연결").click()
                phase_fields = {
                    "source_id": "phase-file",
                    "name": "확인된 3상 전압",
                    "asset_id": asset_id,
                    "measurement_point_id": "panel",
                    "channel_columns": "leg_a,leg_b,leg_c",
                    "timestamp_column": "timestamp",
                }
                for key, value in phase_fields.items():
                    page.locator(f'#file-form input[name="{key}"]').fill(value)
                page.locator('#file-form textarea[name="phase_bindings"]').fill(
                    "\n".join(
                        f"{channel},voltage,{phase},계측기 표시 V 확인,배선도 {phase}상 연결 확인"
                        for channel, phase in (("leg_a", "R"), ("leg_b", "S"), ("leg_c", "T"))
                    )
                )
                page.locator("#csv-upload").set_input_files(
                    {
                        "name": "phase.csv",
                        "mimeType": "text/csv",
                        "buffer": (inputs / "phase.csv").read_bytes(),
                    }
                )
                page.get_by_role("button", name="CSV 분석 전 점검").click()
                pw.expect(page.locator("#csv-preflight-result")).to_contain_text(
                    "3상 R/S/T 매핑 3개 이상 제출됨", timeout=30000
                )
                page.get_by_role("button", name="CSV 확인 후 소스 등록").click()
                phase_card = page.locator('.source-record[data-source-id="phase-file"]')
                pw.expect(phase_card).to_contain_text("검증할 3상 역할 3개", timeout=30000)
                phase_card.get_by_role("button", name="소스 활성화").click()
                pw.expect(phase_card).to_contain_text("관리 상태: active")
                phase_card.get_by_role("button", name="FILE 수신 확인").click()
                pw.expect(phase_card).to_contain_text("FILE 검증 수신 근거 있음")
                phase_card.get_by_role("button", name="저장된 3상 이력 분석 실행").click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "분석 불가", timeout=30000
                )
                assert not SqlitePhaseUnbalanceRepository(
                    workspace.phase_unbalance_state_path
                ).list_results()
                phase_card.get_by_role("button", name="FILE 이력 적재").click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "DuckLake 이력 적재 완료", timeout=30000
                )
                phase_card.get_by_role("button", name="저장된 3상 이력 분석 실행").click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "신규 3상 분석 기록 완료", timeout=30000
                )
                phase_results = SqlitePhaseUnbalanceRepository(
                    workspace.phase_unbalance_state_path
                ).list_results()
                assert len(phase_results) == 1
                phase_analysis = phase_results[0]
                assert phase_analysis.run.source_id == "phase-file"
                assert phase_analysis.evidence.semantic_versions == ("file-web-phase-v1",)
                assert phase_analysis.evidence.results[0].evaluated_samples == 3
                pw.expect(page.locator("#evidence-results")).to_contain_text(
                    phase_analysis.evidence.evidence_id
                )
                page.get_by_role("button", name="이 근거에 사람 검토 요청").click()
                pw.expect(page.locator("#review-results")).to_contain_text(
                    phase_analysis.run.analysis_run_id, timeout=30000
                )
                pw.expect(page.locator("#review-inbox-summary")).to_contain_text("미처리 1건")
                _no_overflow(page, width)
                assert not errors, errors
                assert not external, external
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    assert JsonSourceRepository(workspace.source_registry_path).get("journey-file")
    assert JsonSourceRepository(workspace.source_registry_path).get("phase-file")
    assert SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).list_results() == (
        phase_analysis,
    )
    persisted = JsonFileFeatureAnalysisRepository(workspace.file_feature_analysis_path)
    assert persisted.list_results() == (analysis,)
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
                pw.expect(
                    page.locator("#review-results .review-meaning").filter(
                        has_text="검토 기록 종료됨"
                    )
                ).to_contain_text("실제 정비 완료, 고장 해결 또는 설비 안전 확인의 근거가 아닙니다")
                # The newest FILE source is now phase-file; the history preview
                # must reflect its stored values rather than the earlier vibration CSV.
                pw.expect(page.locator("#last-values")).to_contain_text(
                    "leg_a / phase-file", timeout=30000
                )
                pw.expect(page.locator("#last-values")).to_contain_text("221")
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
                    "active와 수신을 모두 확인한 소스 2개"
                )
                pw.expect(
                    page.get_by_role("button", name="이 근거에 사람 검토 요청")
                ).to_have_count(0)
                pw.expect(page.get_by_role("button", name="검토 기록 종료")).to_have_count(0)
                page.locator("#review-results").get_by_role(
                    "button",
                    name=f"연결된 분석 근거 확인 · {analysis.evidence.evidence_id}",
                ).click()
                target = page.locator("#evidence-results .evidence-target").filter(
                    has_text=analysis.run.analysis_run_id
                )
                pw.expect(target).to_be_focused()
                pw.expect(target).to_contain_text(analysis.evidence.evidence_id)
                pw.expect(page.locator("#evidence-results")).to_contain_text(
                    phase_analysis.evidence.evidence_id
                )
                pw.expect(page.locator("#review-results")).to_contain_text(
                    phase_analysis.run.analysis_run_id
                )
                _no_overflow(page, width)
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    assert len(repository.list_events()) == 3


def test_supervised_web_serializes_separate_http_processes_and_recovers(tmp_path: Path) -> None:
    """Real HTTP subprocesses must share one supervisor writer, even across restart."""
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")

    workspace = OperationsWorkspace(tmp_path / "web")
    init = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(init.config, ui=OperationsUiConfig(port=port))
    )
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n"
        "2026-10-01T00:00:01+00:00,220.7,219.2,221.1\n",
        encoding="utf-8",
    )
    registration = {
        "source_id": "race-file",
        "name": "Concurrent FILE",
        "asset_id": "motor-01",
        "measurement_point_id": "panel",
        "file_path": "inputs/phase.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "timestamp_column": "timestamp",
    }

    def request(
        method: str,
        path: str,
        *,
        token: str = "",
        payload: dict[str, object] | None = None,
        origin: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers.update(
                {
                    "Content-Type": "application/json",
                    "Origin": origin if origin is not None else f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "X-CSRF-Token": token,
                }
            )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    # Python's independent HTTP clients do not have the supervisor's IPC token
    # or PID. Only the authenticated Web child may forward their browser requests.
    client_code = """
import json
import sys
import time
from http.client import HTTPConnection
from pathlib import Path

port, token, client_id, ready_dir, release, payload = sys.argv[1:]
Path(ready_dir, client_id).touch()
deadline = time.monotonic() + 25
while not Path(release).exists():
    if time.monotonic() > deadline:
        raise TimeoutError("HTTP client release gate was not opened")
    time.sleep(0.01)
connection = HTTPConnection("127.0.0.1", int(port), timeout=15)
try:
    connection.request(
        "POST", "/api/v1/sources/file", body=payload,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
            "Sec-Fetch-Site": "same-origin",
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    print(json.dumps({"status": response.status, "body": json.loads(response.read())}))
finally:
    connection.close()
"""
    log = tmp_path / "supervisor.log"
    processes: list[subprocess.Popen[bytes]] = []
    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        assert session["write_scope"] == "supervisor-owned-source-control"
        token = session["csrf_token"]
        assert isinstance(token, str)

        # Different OS processes race through real HTTP -> Web child -> PID-bound
        # IPC -> one durable source repository. A thread-only broker test cannot
        # detect failures in this public request boundary.
        ready_dir = tmp_path / "ready"
        ready_dir.mkdir()
        release = tmp_path / "release"
        for index in range(6):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        client_code,
                        str(port),
                        token,
                        str(index),
                        str(ready_dir),
                        str(release),
                        json.dumps(registration),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        deadline = time.monotonic() + 25
        while len(list(ready_dir.iterdir())) != len(processes):
            if any(child.poll() is not None for child in processes):
                pytest.fail("an HTTP client exited before the release gate")
            if time.monotonic() > deadline:
                pytest.fail("separate HTTP clients did not reach the release gate")
            time.sleep(0.02)
        release.touch()
        results = []
        for child in processes:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0, stderr.decode(errors="replace")
            results.append(json.loads(stdout))
        assert sorted(item["status"] for item in results) == [201, 409, 409, 409, 409, 409]
        assert all(
            item["body"]["error"]["code"] == "source_id_exists"
            for item in results
            if item["status"] == 409
        )
        assert JsonSourceRepository(workspace.source_registry_path).get("race-file")
        assert not workspace.history_catalog_path.exists()
        status, sources = request("GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False

        # Neither a forged origin nor a missing/incorrect CSRF token may cause
        # another mutation, even though both requests reach a live HTTP listener.
        for bad_token, bad_origin in (
            ("invalid", None),
            (token, "https://untrusted.example"),
        ):
            status, error = request(
                "POST",
                "/api/v1/sources/file",
                token=bad_token,
                payload={**registration, "source_id": "unauthorized"},
                origin=bad_origin,
            )
            assert status == 403, error
        assert JsonSourceRepository(workspace.source_registry_path).get("race-file")
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
        _stop(proc, workspace.root)

    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    assert JsonSourceRepository(workspace.source_registry_path).get("race-file")

    # A restarted supervisor must preserve committed data, but its Web CSRF
    # capability is new. Replay of an old mutation is not durable exactly-once.
    proc = _start(workspace.root, port, log)
    try:
        status, new_session = request("GET", "/api/v1/session")
        assert status == 200
        new_token = new_session["csrf_token"]
        assert isinstance(new_token, str) and new_token != token
        status, error = request(
            "POST",
            "/api/v1/sources/file",
            token=token,
            payload={**registration, "source_id": "stale-session"},
        )
        assert status == 403, error
        status, duplicate = request(
            "POST",
            "/api/v1/sources/file",
            token=new_token,
            payload=registration,
        )
        assert status == 409
        assert duplicate["error"]["code"] == "source_id_exists"
        status, sources = request("GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


def test_web_child_sigkill_revokes_old_write_authority_and_preserves_workspace(
    tmp_path: Path,
) -> None:
    """Actual supervised Web SIGKILL must fail closed, then restart from durable state."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "web-kill")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    original_config = workspace.config_path.read_bytes()
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phases.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n",
        encoding="utf-8",
    )
    registration = {
        "source_id": "kill-file",
        "name": "Web failure FILE",
        "asset_id": "motor-01",
        "measurement_point_id": "panel",
        "file_path": "inputs/phases.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "timestamp_column": "timestamp",
    }

    def request(
        method: str,
        route: str,
        *,
        payload: dict[str, object] | None = None,
        csrf: str = "",
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers.update(
                {
                    "Origin": f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf,
                }
            )
        try:
            connection.request(method, route, body=body, headers=headers)
            reply = connection.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            connection.close()

    state_repository = OperationsSupervisorStateRepository(workspace.supervisor_state_path)
    log = tmp_path / "supervisor-kill.log"
    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        csrf = session["csrf_token"]
        assert isinstance(csrf, str)
        assert session["write_scope"] == "supervisor-owned-source-control"
        status, created = request("POST", "/api/v1/sources/file", payload=registration, csrf=csrf)
        assert status == 201 and created["registration_state"] == "registered"
        assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 1
        assert not workspace.history_catalog_path.exists()

        running = state_repository.load()
        assert running is not None
        assert running.state == OperationsSupervisorStateKind.RUNNING
        assert running.supervisor_pid == proc.pid
        ui = next(item for item in running.components if item.kind == OperationsComponentKind.UI)
        assert ui.pid != proc.pid
        # Kill only the PID verified against the active supervisor state.
        # The supervisor must stop its other children and release writer ownership.
        os.kill(ui.pid, signal.SIGKILL)
        assert proc.wait(timeout=35) != 0
        failed = state_repository.load()
        assert failed is not None
        assert failed.state == OperationsSupervisorStateKind.FAILED
        assert failed.supervisor_pid == proc.pid
        assert failed.failure is not None and "ui exited with code" in failed.failure
        killed_ui = next(
            item for item in failed.components if item.kind == OperationsComponentKind.UI
        )
        assert killed_ui.return_code == -signal.SIGKILL
        with pytest.raises(OSError):
            request("GET", "/api/v1/session")
        assert workspace.config_path.read_bytes() == original_config
        assert JsonSourceRepository(workspace.source_registry_path).get("kill-file")
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)

    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        new_csrf = session["csrf_token"]
        assert isinstance(new_csrf, str) and new_csrf != csrf
        status, rejected = request(
            "POST",
            "/api/v1/sources/file",
            payload={**registration, "source_id": "stale-session"},
            csrf=csrf,
        )
        assert status == 403 and rejected == {"error": {"code": "write_not_authorized"}}
        status, duplicate = request(
            "POST", "/api/v1/sources/file", payload=registration, csrf=new_csrf
        )
        assert status == 409
        assert duplicate == {"error": {"code": "source_id_exists"}}
        status, sources = request("GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        row = sources["sources"]["items"][0]
        assert row["source_id"] == "kill-file" and row["receipt_confirmed"] is False
        assert workspace.config_path.read_bytes() == original_config
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


def test_independent_preview_process_cannot_mutate_supervised_workspace(
    tmp_path: Path,
) -> None:
    """Only the supervisor may write until its real cross-process lease is released."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "supervised-and-preview")
    initialized = initialize_operations_workspace(workspace)
    supervisor_port = _port()
    preview_port = _port()
    while preview_port == supervisor_port:
        preview_port = _port()
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=OperationsUiConfig(port=supervisor_port)),
    )
    original_config = workspace.config_path.read_bytes()
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n",
        encoding="utf-8",
    )
    registration = {
        "source_id": "owner-file",
        "name": "Supervisor FILE",
        "asset_id": "motor-01",
        "measurement_point_id": "panel",
        "file_path": "inputs/phase.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "timestamp_column": "timestamp",
    }

    def request(
        port: int,
        route: str,
        *,
        payload: dict[str, object] | None = None,
        token: str = "",
        origin: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers.update(
                {
                    "Origin": origin if origin is not None else f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "X-CSRF-Token": token,
                    "Content-Type": "application/json",
                }
            )
        try:
            connection.request("POST" if payload is not None else "GET", route, body, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    # The preview has a different PID, HTTP port and CSRF generation from
    # the supervised Web child. It must never borrow the supervisor IPC token.
    preview_script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from industrial_phm.runtime.operations_web_http import create_operations_web_read_server\n"
        "server = create_operations_web_read_server(Path(sys.argv[1]), port=int(sys.argv[2]))\n"
        "server.serve_forever()\n"
    )
    supervisor_log = tmp_path / "supervisor.log"
    preview_log = tmp_path / "preview.log"
    supervisor = _start(workspace.root, supervisor_port, supervisor_log)
    try:
        with preview_log.open("wb") as output:
            preview = subprocess.Popen(
                [sys.executable, "-c", preview_script, str(workspace.root), str(preview_port)],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        try:
            deadline = time.monotonic() + 20
            while True:
                if preview.poll() is not None:
                    pytest.fail(
                        "independent Web preview exited: "
                        + preview_log.read_text(errors="replace")[-4000:]
                    )
                try:
                    preview_status, preview_session = request(preview_port, "/api/v1/session")
                    if preview_status == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    pytest.fail("independent Web preview did not start")
                time.sleep(0.1)
            assert preview_session["write_scope"] == "local-source-control-and-opcua-preview"
            preview_csrf = preview_session["csrf_token"]
            assert isinstance(preview_csrf, str)
            status, supervisor_session = request(supervisor_port, "/api/v1/session")
            assert status == 200
            assert supervisor_session["write_scope"] == "supervisor-owned-source-control"
            supervisor_csrf = supervisor_session["csrf_token"]
            assert isinstance(supervisor_csrf, str) and supervisor_csrf != preview_csrf

            status, created = request(
                supervisor_port,
                "/api/v1/sources/file",
                payload=registration,
                token=supervisor_csrf,
            )
            assert status == 201 and created["registration_state"] == "registered"
            status, visible = request(preview_port, "/api/v1/sources")
            assert status == 200 and visible["sources"]["total"] == 1

            # Concurrent valid same-origin preview POSTs must fail on the actual
            # supervisor's OS-level workspace lease before reaching any facade.
            routes = sorted(WEB_SOURCE_ACTION_ROUTES - WEB_SUPERVISOR_ONLY_ACTION_ROUTES)
            blocked = {**registration, "source_id": "blocked-preview"}

            def attempt(route: str) -> tuple[str, int, dict[str, object]]:
                status, response = request(preview_port, route, payload=blocked, token=preview_csrf)
                return route, status, response

            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(attempt, routes))
            assert len(responses) == len(routes)
            assert all(
                status == 409 and body == {"error": {"code": "workspace_writer_busy"}}
                for _, status, body in responses
            ), responses
            for route in WEB_SUPERVISOR_ONLY_ACTION_ROUTES:
                status, result = request(preview_port, route, payload={}, token=preview_csrf)
                assert status == 403 and result == {"error": {"code": "supervisor_required"}}
            status, result = request(
                preview_port,
                "/api/v1/sources/file",
                payload=blocked,
                token=supervisor_csrf,
            )
            assert status == 403 and result == {"error": {"code": "write_not_authorized"}}
            status, result = request(
                preview_port,
                "/api/v1/sources/file",
                payload=blocked,
                token=preview_csrf,
                origin="https://untrusted.example",
            )
            assert status == 403 and result == {"error": {"code": "origin_not_allowed"}}

            # Live supervisor writes must still succeed; preview cannot modify
            # either the registry or received/collected history.
            status, created = request(
                supervisor_port,
                "/api/v1/sources/file",
                payload={**registration, "source_id": "owner-file-two"},
                token=supervisor_csrf,
            )
            assert status == 201 and created["registration_state"] == "registered"
            assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 2
            assert not workspace.history_catalog_path.exists()
            assert workspace.config_path.read_bytes() == original_config

            # Release the owner lease before trying the identical preview write.
            # No process restart, permission escalation or stale lock workaround.
            _stop(supervisor, workspace.root)
            assert supervisor.returncode == 0, supervisor_log.read_text(errors="replace")[-4000:]
            assert preview.poll() is None
            status, saved = request(
                preview_port, "/api/v1/sources/file", payload=blocked, token=preview_csrf
            )
            assert status == 201 and saved["registration_state"] == "registered"
            status, visible = request(preview_port, "/api/v1/sources")
            assert status == 200 and visible["sources"]["total"] == 3
            assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 3
            assert not workspace.history_catalog_path.exists()
            assert workspace.config_path.read_bytes() == original_config
        finally:
            if preview.poll() is None:
                preview.terminate()
            preview.wait(timeout=15)
    finally:
        _stop(supervisor, workspace.root)
