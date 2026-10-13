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
from datetime import UTC, datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonFileFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.application.phase_unbalance import PhaseUnbalanceAnalysis
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


@pytest.mark.parametrize("width", [390, 1440])
def test_supervised_web_csv_first_data_reaches_stored_monitor_graph(
    tmp_path: Path, width: int
) -> None:
    """Empty workspace → CSV preview → server check → visible writes → measured graph."""
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
    files = tmp_path / "files"
    files.mkdir()
    (files / "naive.csv").write_text(
        "time,current_r,current_s\n2020-03-02 09:00:00,1.0,2.0\n2020-03-02 09:00:10,,2.1\n",
        encoding="utf-8",
    )
    kst = timezone(timedelta(hours=9))
    start = datetime(2020, 3, 2, 9, 0, tzinfo=kst)
    # Large enough that storing history takes longer than one bounded 5 s Web command.
    rows = [(seconds, round(12 + seconds / 100000, 3)) for seconds in range(0, 360000, 10)]
    (files / "motor.csv").write_text(
        "timestamp,current_r,current_s,status\n"
        + "".join(
            f"{(start + timedelta(seconds=s)).isoformat()},{v},{v + 1},RUN\n" for s, v in rows
        ),
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
            try:
                page.goto(f"http://127.0.0.1:{port}/web/", wait_until="domcontentloaded")
                pw.expect(page.locator("#workspace-start")).to_be_visible(timeout=30000)
                pw.expect(page.locator("#phm-monitor")).to_be_hidden()
                page.get_by_role("link", name="파일에서 시작").click()
                chooser = page.locator("#csv-start-file")
                pw.expect(chooser).to_be_focused()

                # An unsupported file is explained by row before anything is written.
                chooser.set_input_files(str(files / "naive.csv"))
                issues = page.locator("#csv-start-issues")
                pw.expect(issues).to_contain_text("시간대")
                pw.expect(issues).to_contain_text("current_r 컬럼의 3행이 비어 있습니다")
                page.locator("#csv-start-asset").fill("motor-01")
                page.get_by_role("button", name="서버에서 파일 점검 (저장 안 함)").click()
                check = page.locator("#csv-start-check-result")
                pw.expect(check).to_contain_text("3행", timeout=30000)
                pw.expect(page.get_by_role("button", name="등록하고 이력 저장")).to_be_disabled()
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()
                assert not (workspace.root / "web-uploads").exists()

                # A supported file shows its own values; a text column is not stored.
                chooser.set_input_files(str(files / "motor.csv"))
                pw.expect(page.locator("#csv-start-chart svg")).to_be_visible()
                pw.expect(issues).to_contain_text("구조 문제는 없습니다")
                status = page.locator('#csv-start-channels input[value="status"]')
                pw.expect(status).to_be_disabled()
                pw.expect(status).not_to_be_checked()
                pw.expect(page.locator("#csv-start-asset")).to_have_value("motor-01")
                page.get_by_role("button", name="서버에서 파일 점검 (저장 안 함)").click()
                pw.expect(check).to_contain_text("서버 점검 통과", timeout=30000)
                pw.expect(check).to_contain_text("2020-03-02 09:00:00 KST")
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()

                # A failed later write keeps inputs, and a retry never registers twice.
                page.route(
                    "**/api/v1/sources/file/backfill/start",
                    lambda route: route.fulfill(
                        status=503, json={"error": {"code": "source_state_unavailable"}}
                    ),
                )
                page.get_by_role("button", name="등록하고 이력 저장").click()
                steps = page.locator("#csv-start-save-steps")
                pw.expect(steps.locator('[data-step="store"]')).to_contain_text(
                    "실패", timeout=60000
                )
                pw.expect(steps.locator('[data-step="receive"]')).to_contain_text("완료")
                pw.expect(page.locator("#csv-start-save-result")).to_contain_text(
                    "완료된 단계는 건너뜁니다"
                )
                pw.expect(page.locator("#csv-start-asset")).to_have_value("motor-01")
                assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 1
                assert not workspace.history_catalog_path.exists()
                page.unroute("**/api/v1/sources/file/backfill/start")
                with page.expect_response(lambda r: "/api/v1/sources/file/backfill/start" in r.url):
                    page.get_by_role("button", name="실패한 단계부터 다시 시도").click()
                # Browser lifecycle cannot cancel the supervisor's write. Re-selecting the same
                # bytes restores the pending input and verifies identity before resuming.
                page.reload()
                chooser.set_input_files(str(files / "motor.csv"))
                pw.expect(page.locator("#csv-start-file-state")).to_contain_text(
                    "이전 작업 입력 복원"
                )
                pw.expect(page.locator("#csv-start-asset")).to_have_value("motor-01")
                page.get_by_role("button", name="서버에서 파일 점검 (저장 안 함)").click()
                pw.expect(check).to_contain_text("기존 파일·설정과 동일", timeout=30000)
                page.get_by_role("button", name="등록하고 이력 저장").click()
                pw.expect(steps.locator('[data-step="store"]')).to_contain_text(
                    f"측정값 {len(rows) * 2:,}개", timeout=180000
                )
                sources = JsonSourceRepository(workspace.source_registry_path).list_sources()
                assert len(sources) == 1
                source_id = sources[0].source_id
                assert workspace.history_catalog_path.exists()

                page.get_by_role("button", name="모니터링에서 실제 그래프 보기").click()
                pw.expect(page.locator('nav a[href="#monitor"]')).to_have_attribute(
                    "aria-current", "page"
                )
                selected = page.locator('.monitor-asset[aria-pressed="true"]')
                pw.expect(selected).to_contain_text("motor-01", timeout=30000)
                reading = page.locator("#monitor-signal-reading")
                pw.expect(reading).to_contain_text(f"{rows[-1][1]:g}", timeout=30000)
                last_at = start + timedelta(seconds=rows[-1][0])
                pw.expect(reading).to_contain_text(
                    "원본 측정 " + last_at.strftime("%Y-%m-%d %H:%M:%S") + " KST"
                )
                pw.expect(page.locator("#monitor-signal-chart .monitor-raw-line")).to_have_count(1)
                pw.expect(page.locator("#monitor-history-range")).to_have_value("7d")

                # The real server refuses a duplicate source; inputs stay for correction.
                page.locator('nav a[href="#connect"]').click()
                page.get_by_role("button", name="다른 파일로 시작").click()
                (files / "motor.csv").write_text(
                    (files / "motor.csv").read_text().replace(",RUN", ",STOP")
                )
                chooser.set_input_files(str(files / "motor.csv"))
                page.locator("#csv-start-asset").fill("motor-01")
                page.locator(".csv-start-advanced > summary").click()
                page.locator("#csv-start-source-id").fill(source_id)
                page.get_by_role("button", name="서버에서 파일 점검 (저장 안 함)").click()
                pw.expect(check).to_contain_text(
                    "기존 파일·측정 컬럼·설정이 다릅니다", timeout=30000
                )
                pw.expect(page.locator("#csv-start-save")).to_be_disabled()
                pw.expect(page.locator("#csv-start-asset")).to_be_enabled()
                pw.expect(page.locator("#csv-start-asset")).to_have_value("motor-01")
                assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 1
                _no_overflow(page, width)
                assert not errors, errors
                assert not external, external
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


def test_supervised_web_one_click_example_opens_monitoring_without_duplicates(
    tmp_path: Path,
) -> None:
    """A real isolated demo stays separate; its measurements cannot mutate the parent."""
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
    log = tmp_path / "supervisor.log"
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="ko-KR")
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            try:
                page.goto(f"http://127.0.0.1:{port}/web/", wait_until="domcontentloaded")
                page.get_by_role("button", name="예시 데이터로 둘러보기").click(timeout=30000)
                pw.expect(page.locator(".synthetic-context")).to_contain_text(
                    "읽기 전용", timeout=60000
                )
                assert page.url.startswith("http://127.0.0.1:")
                assert not page.url.startswith(f"http://127.0.0.1:{port}/")
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()
                pw.expect(page.locator("#monitor-signal-chart svg").first).to_be_visible(
                    timeout=60000
                )
                session = page.request.get(page.url.split("/web/")[0] + "/api/v1/session").json()
                assert session["write_scope"] == "read-only-synthetic-demo"
                page.get_by_role("link", name="내 작업공간으로 돌아가기").click()
                pw.expect(page.locator("#workspace-start")).to_be_visible(timeout=30000)
                # Reopening the owned demo does not mix data into the parent's source catalogue.
                page.get_by_role("button", name="예시 데이터로 둘러보기").click()
                pw.expect(page.locator(".synthetic-context")).to_be_visible(timeout=30000)
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()
                page.get_by_role("link", name="내 작업공간으로 돌아가기").click()
                page.get_by_role("link", name="파일에서 시작").click()
                page.get_by_role("button", name="합성 CSV 미리보기 · 저장하지 않음").click()
                page.get_by_role("button", name="서버에서 파일 점검 (저장 안 함)").click()
                pw.expect(page.locator("#csv-start-check-result")).to_contain_text("미리보기 전용")
                pw.expect(page.locator("#csv-start-save")).to_be_disabled()
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


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
                page.locator('nav a[href="#system"]').click()
                page.get_by_role("button", name="실행 상태 다시 확인").click()
                pw.expect(page.locator("#runtime-facts")).to_contain_text(str(proc.pid))
                page.locator('nav a[href="#connect"]').click()
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
                page.locator("#operator-guide > summary").click()
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
                page.get_by_role("link", name="데이터 연결", exact=True).click()
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
                pw.expect(page.locator("#csv-preflight-result")).to_contain_text("표본 3행")
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
                page.locator('nav a[href="#connect"]').click()
                pw.expect(handoff).to_be_visible()
                assert not workspace.history_catalog_path.exists()
                handoff.click()
                pw.expect(page.locator('nav a[href="#monitor"]')).to_have_attribute(
                    "aria-current", "page"
                )
                page.locator('nav a[href="#connect"]').click()
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
                page.get_by_role("link", name="분석 결과").click()
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
                page.get_by_role("link", name="분석 결과").click()
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
                page.get_by_role("link", name="데이터 연결", exact=True).click()
                phase_fields = {
                    "source_id": "phase-file",
                    "name": "확인된 3상 전압",
                    "asset_id": asset_id,
                    "measurement_point_id": "panel",
                    "channel_columns": "leg_a,leg_b,leg_c",
                    "timestamp_column": "timestamp",
                }
                page.locator("#advanced-file-registration").evaluate("el => el.open = true")
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
                page.locator('nav a[href="#connect"]').click()
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
                page.locator('nav a[href="#connect"]').click()
                pw.expect(handoff).to_be_visible()
                pw.expect(page.locator("#onboarding-steps")).to_contain_text(
                    "active와 수신을 모두 확인한 소스 2개"
                )
                pw.expect(
                    page.get_by_role("button", name="이 근거에 사람 검토 요청")
                ).to_have_count(0)
                pw.expect(page.get_by_role("button", name="검토 기록 종료")).to_have_count(0)
                page.locator('nav a[href="#review"]').click()
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


@pytest.mark.parametrize("width", [1024, 1440])
def test_supervised_web_keeps_cross_asset_review_evidence_and_system_state_exact(
    tmp_path: Path, width: int
) -> None:
    """Two persisted analyses, real Supervisor IPC, cross-asset review and system recovery.

    This tests the currently supported Analysis Evidence / Human Review / System
    screens; it does not pretend the retired Investigation/Maintenance UI exists.
    """
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "cross-asset")
    init = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(init.config, ui=OperationsUiConfig(port=port))
    )
    first = phase_unbalance_analysis()
    second_run_id = "analysis-second-asset"
    second_source_id = "other-site-opcua"
    second_asset_id = "motor-8"
    second = PhaseUnbalanceAnalysis(
        run=replace(
            first.run,
            analysis_run_id=second_run_id,
            source_id=second_source_id,
            asset_id=second_asset_id,
        ),
        evidence=replace(
            first.evidence,
            evidence_id="evidence-second-asset",
            analysis_run_id=second_run_id,
            source_id=second_source_id,
            input_reference=replace(
                first.evidence.input_reference,
                source_id=second_source_id,
                asset_id=second_asset_id,
                window_id="window-second-asset",
            ),
        ),
    )
    analyses = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    analyses.record(first)
    analyses.record(second)
    log = tmp_path / "cross-asset-supervisor.log"
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.on("dialog", lambda dialog: dialog.accept())
                page.goto(f"http://127.0.0.1:{port}/web/", wait_until="domcontentloaded")
                selector = page.locator("#asset-select")
                pw.expect(selector).to_be_enabled(timeout=30000)

                # The real stored System status must not become a false green
                # merely because an earlier snapshot was loaded successfully.
                pw.expect(page.locator("#runtime-facts")).to_contain_text(
                    str(proc.pid), timeout=30000
                )
                page.route("**/api/v1/system/runtime", lambda route: route.abort("failed"))
                page.locator('nav a[href="#system"]').click()
                page.get_by_role("button", name="실행 상태 다시 확인").click()
                pw.expect(page.locator("#runtime-status")).to_contain_text(
                    "실행 상태 조회 실패", timeout=30000
                )
                pw.expect(page.locator("#runtime-facts")).to_be_empty()
                pw.expect(page.locator("#runtime-components")).to_be_empty()
                page.unroute("**/api/v1/system/runtime")
                page.locator('nav a[href="#system"]').click()
                page.get_by_role("button", name="실행 상태 다시 확인").click()
                pw.expect(page.locator("#runtime-facts")).to_contain_text(
                    str(proc.pid), timeout=30000
                )
                pw.expect(page.locator("#runtime-components")).to_contain_text("Web 화면")

                page.locator('nav a[href="#evidence"]').click()
                selector.select_option(first.run.asset_id)
                evidence = page.locator("#evidence-results")
                review = page.locator("#review-results")
                pw.expect(evidence).to_contain_text(first.evidence.evidence_id)
                pw.expect(evidence).not_to_contain_text(second.evidence.evidence_id)
                page.get_by_role("button", name="이 근거에 사람 검토 요청").click()
                pw.expect(page.locator("#review-inbox-summary")).to_contain_text(
                    "미처리 1건", timeout=30000
                )
                pw.expect(review).to_contain_text(first.run.analysis_run_id)
                pw.expect(review).not_to_contain_text(second.run.analysis_run_id)

                selector.select_option(second_asset_id)
                pw.expect(evidence).to_contain_text(second.evidence.evidence_id)
                pw.expect(evidence).not_to_contain_text(first.evidence.evidence_id)
                pw.expect(review).not_to_contain_text(first.run.analysis_run_id)
                pw.expect(review).to_contain_text("이 설비에 기록된 검토 요청이 없습니다")
                inbox = page.locator("#review-inbox-list")
                pw.expect(inbox).to_contain_text(first.run.analysis_run_id)
                pw.expect(inbox).to_contain_text(first.evidence.evidence_id)

                # The global inbox switches selected asset, exact Run/Evidence
                # and keyboard focus; it must not open the newer asset's record.
                first_finding_id = "finding-review-" + first.run.analysis_run_id
                page.locator('nav a[href="#review"]').click()
                inbox.get_by_role(
                    "button",
                    name=f"검토 열기 · {first.run.asset_id} · {first_finding_id}",
                ).click()
                pw.expect(selector).to_have_value(first.run.asset_id)
                pw.expect(review.locator(".review-record")).to_be_focused()
                pw.expect(review).to_contain_text(first.evidence.evidence_id)
                pw.expect(review).not_to_contain_text(second.evidence.evidence_id)
                review.get_by_role(
                    "button", name=f"연결된 분석 근거 확인 · {first.evidence.evidence_id}"
                ).click()
                pw.expect(evidence.locator(".evidence-target")).to_be_focused()
                pw.expect(evidence).not_to_contain_text(second.evidence.evidence_id)

                selector.select_option(second_asset_id)
                page.locator('nav a[href="#evidence"]').click()
                page.get_by_role("button", name="이 근거에 사람 검토 요청").click()
                pw.expect(page.locator("#review-inbox-summary")).to_contain_text(
                    "미처리 2건", timeout=30000
                )
                pw.expect(review).to_contain_text(second.run.analysis_run_id)
                pw.expect(review).not_to_contain_text(first.run.analysis_run_id)
                pw.expect(inbox).to_contain_text(first.run.analysis_run_id)
                pw.expect(inbox).to_contain_text(second.run.analysis_run_id)
                _no_overflow(page, width)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    review_store = JsonFindingReviewRepository(workspace.maintenance_review_state_path)
    assert len(review_store.list_events()) == 0
    stored = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
    assert {item.analysis_run_id for item in stored} == {
        first.run.analysis_run_id,
        second.run.analysis_run_id,
    }

    # Both finding identities must remain stable after a real supervisor restart.
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                # The default route is the Monitor; the review asset selector belongs to #review.
                page.goto(f"http://127.0.0.1:{port}/web/#review", wait_until="domcontentloaded")
                pw.expect(page.locator("#review-inbox-summary")).to_contain_text(
                    "미처리 2건", timeout=30000
                )
                selector = page.locator("#asset-select")
                selector.select_option(second_asset_id)
                pw.expect(page.locator("#review-results")).to_contain_text(
                    second.evidence.evidence_id
                )
                pw.expect(page.locator("#review-results")).not_to_contain_text(
                    first.evidence.evidence_id
                )
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


@pytest.mark.parametrize("width", [1024, 1440])
def test_supervised_web_opcua_browse_live_history_disconnect_and_reconnect(
    tmp_path: Path, width: int
) -> None:
    """Real Web commands, collector-owned live history and an observed OPC UA outage.

    A one-shot Web diagnostic is not continuous collection. The simulator is a
    separate real OPC UA server process, restarted on the *same* endpoint; only
    the supervised collector may commit the resulting history to DuckLake.
    """
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("asyncua")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

    workspace = OperationsWorkspace(tmp_path / "opcua-live-browser")
    initialized = initialize_operations_workspace(workspace)
    web_port, opcua_port = _port(), _port()
    while opcua_port == web_port:
        opcua_port = _port()
    endpoint = f"opc.tcp://127.0.0.1:{opcua_port}/phm-demo/"
    source_id = "browser-live-opcua"
    asset_id = "browser-motor"
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=OperationsUiConfig(port=web_port)),
    )
    simulator_log = tmp_path / "opcua-server.log"
    supervisor_log = tmp_path / "opcua-supervisor.log"

    def simulator_start() -> subprocess.Popen[bytes]:
        log_offset = simulator_log.stat().st_size if simulator_log.exists() else 0
        with simulator_log.open("ab") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tools.opcua.demo",
                    "server",
                    "--endpoint",
                    endpoint,
                    "--profile",
                    "power",
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        until = time.monotonic() + 35
        while time.monotonic() < until:
            if process.poll() is not None:
                pytest.fail(
                    "OPC UA simulator terminated before ready: "
                    + simulator_log.read_text(errors="replace")[-4000:]
                )
            if "Synthetic OPC UA server:" in simulator_log.read_text(errors="replace")[log_offset:]:
                return process
            time.sleep(0.2)
        simulator_stop(process)
        pytest.fail("OPC UA simulator readiness timeout")

    def simulator_stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def until_evidence(name: str, predicate, *, timeout: float = 85.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.4)
        pytest.fail(
            f"Missing {name}\nsimulator:\n"
            + simulator_log.read_text(errors="replace")[-4000:]
            + "\nsupervisor:\n"
            + supervisor_log.read_text(errors="replace")[-4000:]
        )

    def source_row(page):
        response = page.request.get(f"http://127.0.0.1:{web_port}/api/v1/sources")
        assert response.ok, (response.status, response.text()[:500])
        payload = response.json()
        assert payload["schema_version"] == 1
        return next(
            (item for item in payload["sources"]["items"] if item["source_id"] == source_id),
            None,
        )

    def matching_source(page, predicate):
        row = source_row(page)
        return row if row is not None and predicate(row) else None

    def browser_evidence(page, stage: str) -> None:
        if root := os.environ.get("PHM_FIRST_RUN_SCREENSHOTS"):
            target = Path(root)
            target.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target / f"opcua-{width}-{stage}.png"), full_page=True)

    simulator = simulator_start()
    supervisor: subprocess.Popen[bytes] | None = None
    try:
        supervisor = _start(workspace.root, web_port, supervisor_log)
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())
                page.goto(f"http://127.0.0.1:{web_port}/web/", wait_until="domcontentloaded")
                pw.expect(page.locator("#runtime-facts")).to_contain_text(
                    str(supervisor.pid), timeout=30000
                )
                pw.expect(page.locator("#onboarding-state")).to_contain_text(
                    "소스 미등록", timeout=30000
                )
                page.get_by_role("link", name="데이터 연결", exact=True).click()
                page.locator("#opcua-registration > summary").click()
                page.locator("#opcua-endpoint").fill(endpoint)
                page.get_by_role("button", name="로컬 변수 탐색").click()
                # Server internals can consume the bounded root browse budget.
                # Narrowing to the discovered synthetic object must recover the
                # actual variable candidate without reading values or saving a source.
                browse_result = page.locator("#opcua-browse-result")
                pw.expect(browse_result).to_contain_text("변수 후보", timeout=30000)
                pw.expect(browse_result).to_contain_text(
                    "SyntheticPower 객체 내부 탐색", timeout=30000
                )
                browse_result.get_by_role("button", name="SyntheticPower 객체 내부 탐색").click()
                pw.expect(browse_result).to_contain_text("ns=2;s=active_power", timeout=30000)
                pw.expect(browse_result).to_contain_text("수신 근거 아님")
                assert source_row(page) is None
                assert not workspace.history_catalog_path.exists()

                form = page.locator("#opcua-form")
                for name, value in (
                    ("source_id", source_id),
                    ("name", "Browser live OPC UA"),
                    ("asset_id", asset_id),
                ):
                    form.locator(f'input[name="{name}"]').fill(value)
                form.locator('textarea[name="node_mappings"]').fill(
                    "active_power=ns=2;s=active_power\nvoltage=ns=2;s=voltage"
                )
                page.get_by_role("button", name="OPC UA 매핑 등록").click()
                listing = page.locator("#source-list")
                pw.expect(listing).to_contain_text(source_id, timeout=30000)
                pw.expect(listing).to_contain_text("수신 근거 미확인")
                assert not workspace.history_catalog_path.exists()

                listing.get_by_role("button", name="소스 활성화").click()
                pw.expect(listing).to_contain_text("관리 상태: active")
                listing.get_by_role("button", name="OPC UA 1회 수신 진단").click()
                pw.expect(page.locator("#source-control-result")).to_contain_text(
                    "수신 근거 기록 완료", timeout=30000
                )
                assert source_row(page)["last_live_history_committed_at"] is None

                listing.get_by_role("button", name="수집 시작 요청").click()
                pw.expect(listing).to_contain_text("연속 수집 요청: running")
                first = until_evidence(
                    "collector live receive and DuckLake commit",
                    lambda: matching_source(
                        page,
                        lambda row: (
                            str(row["opcua_session_last_state"]).upper() == "CONNECTED"
                            and row["last_live_received_at"] is not None
                            and row["last_live_history_snapshot_id"] is not None
                        ),
                    ),
                )
                first_snapshot = first["last_live_history_snapshot_id"]
                first_received = first["last_live_received_at"]
                page.locator("#refresh").click()
                pw.expect(listing).to_contain_text(
                    "OPC UA 이력 저장(DuckLake 커밋):", timeout=30000
                )
                pw.expect(page.locator("#last-values")).to_contain_text(source_id, timeout=30000)
                pw.expect(page.locator("#last-values")).to_contain_text("현재 상태가 아님")
                browser_evidence(page, "receiving")

                simulator_stop(simulator)
                disconnected = until_evidence(
                    "collector-observed disconnect",
                    lambda: matching_source(
                        page,
                        lambda row: (
                            row["opcua_session_last_state"] is not None
                            and str(row["opcua_session_last_state"]).upper() != "CONNECTED"
                        ),
                    ),
                )
                assert disconnected["last_live_history_snapshot_id"] is not None
                assert disconnected["collection_desired_state"] == "running"
                page.locator("#refresh").click()
                # A disconnected worker can transition STOPPED → CONNECTING while
                # this read is in flight. The UI must keep the *meaning* unknown;
                # matching the earlier enum snapshot would be a race.
                pw.expect(listing).to_contain_text("OPC UA 세션 마지막 기록:", timeout=30000)
                pw.expect(listing).to_contain_text("현재 연결 미확인")
                pw.expect(listing).not_to_contain_text("OPC UA 세션 마지막 기록: CONNECTED")
                pw.expect(page.locator("#last-values")).to_contain_text(
                    "마지막 저장된 측정값 · 현재 상태가 아님"
                )
                browser_evidence(page, "disconnected")

                simulator = simulator_start()
                recovered = until_evidence(
                    "same-source reconnect, new live receive and new DuckLake snapshot",
                    lambda: matching_source(
                        page,
                        lambda row: (
                            str(row["opcua_session_last_state"]).upper() == "CONNECTED"
                            and row["last_live_received_at"] != first_received
                            and row["last_live_history_snapshot_id"] not in (None, first_snapshot)
                        ),
                    ),
                )
                assert recovered["source_id"] == source_id
                assert recovered["asset_id"] == asset_id
                page.locator("#refresh").click()
                pw.expect(listing).to_contain_text(
                    "OPC UA 세션 마지막 기록: " + str(recovered["opcua_session_last_state"])
                )
                pw.expect(page.locator("#last-values")).to_contain_text(source_id, timeout=30000)
                browser_evidence(page, "recovered")
                _no_overflow(page, width)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        if supervisor is not None:
            _stop(supervisor, workspace.root)
        simulator_stop(simulator)

    assert supervisor is not None and supervisor.returncode == 0
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    events = history.query_opcua_events(source_id)
    assert events, "Collection must commit real OPC UA events, not only a one-shot receipt"
    identities = [event.local_delivery_identity for event in events]
    assert len(identities) == len(set(identities)), "Reconnect duplicated persisted delivery"
    assert all(event.source_id == source_id for event in events)
