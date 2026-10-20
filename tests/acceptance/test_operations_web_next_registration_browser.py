"""3-phase CSV roles, a local OPC UA server and the isolated sample, from 운영 관리."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from industrial_phm.application import JsonSourceRepository, SqlitePhaseUnbalanceRepository
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from tests.support.opcua import local_opcua_server
from tests.support.web_next import start_web, stop_web

PHASES = (
    "timestamp,leg_a,leg_b,leg_c\n"
    "2026-10-08T12:00:00+00:00,220.0,225.0,230.0\n"
    "2026-10-08T12:00:01+00:00,222.0,226.0,231.0\n"
    "2026-10-08T12:00:02+00:00,221.0,224.0,228.0\n"
)


def _fill(scope: Any, values: dict[str, str]) -> None:
    for label, value in values.items():
        scope.get_by_label(label, exact=True).fill(value)


@pytest.mark.parametrize("width", [390, 1280])
def test_phase_roles_opcua_and_sample_registration(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("asyncua")
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    (workspace.root / "inputs").mkdir()
    (workspace.root / "inputs" / "phases.csv").write_text(PHASES, encoding="utf-8")
    root = workspace.root.resolve()
    server, thread = start_web(root, writer=True)
    try:
        with local_opcua_server() as (endpoint, node_id), pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                sample = {"state": "stopped"}

                def demo(route: Any) -> None:
                    action = route.request.url.rsplit("/", 1)[1]
                    if action in {"start", "stop"}:
                        sample["state"] = "running" if action == "start" else "stopped"
                    body: dict[str, object] = {"schema_version": 1, "synthetic": True, **sample}
                    if sample["state"] == "running":
                        body |= {"separate_workspace": True, "url": "http://127.0.0.1:2799/web/"}
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(body)
                    )

                # The sample would start another local process; its answers are fixed here.
                page.route("**/api/v1/demo/synthetic/*", demo)
                page.goto(f"http://127.0.0.1:{server.server_port}/web/?page=system")
                register = page.get_by_role("region", name="다른 방법으로 연결")

                register.get_by_text("작업공간 안 CSV · 3상 역할 지정").click()
                csv = register.locator("details").filter(has_text="작업공간 안 CSV · 3상 역할 지정")
                _fill(
                    csv,
                    {
                        "연결 ID": "phase-file",
                        "연결 이름": "3상 전압",
                        "설비": "motor-01",
                        "작업공간 안 CSV 경로 (파일을 고르지 않을 때)": "inputs/phases.csv",
                        "측정값 열 (쉼표로 구분)": "leg_a,leg_b,leg_c",
                        "시각 열": "timestamp",
                    },
                )
                roles = register.get_by_role(
                    "group", name="3상 역할 (선택 · 부하·불평형 분석에 필요)"
                )
                for phase, column in (("R", "leg_a"), ("S", "leg_b"), ("T", "leg_c")):
                    roles.get_by_label(f"전압 {phase}상").select_option(column)
                for field in roles.get_by_label("단위 근거").all():
                    field.fill("계측기 표시 V 확인")
                for field in roles.get_by_label("해석 근거").all():
                    field.fill("배선도에서 상 확인")
                csv.get_by_role("button", name="점검 (저장 안 함)").click()
                pw.expect(csv.get_by_text("3상 역할 3개")).to_be_visible()
                csv.get_by_role("button", name="연결 등록").click()
                pw.expect(csv.get_by_text("연결 phase-file을 등록했습니다")).to_be_visible()
                source = JsonSourceRepository(workspace.source_registry_path).get("phase-file")
                assert len(source.config.semantic_bindings) == 3

                card = page.get_by_role("region", name="등록한 연결").get_by_role(
                    "article", name="3상 전압"
                )
                for step in ("이 연결 사용하기", "파일 읽기 확인", "측정 이력 저장"):
                    card.get_by_role("button", name=step).click()
                    pw.expect(card.get_by_role("button", name=step)).to_have_count(
                        0, timeout=20_000
                    )
                card.get_by_text("다른 작업").click()
                card.get_by_role("button", name="3상 불평형 분석").click()
                pw.expect(card.get_by_role("status")).to_contain_text(
                    "3상 불평형 분석을 저장했습니다"
                )
                assert (
                    len(
                        SqlitePhaseUnbalanceRepository(
                            workspace.phase_unbalance_state_path
                        ).list_results()
                    )
                    == 1
                )

                register.get_by_text("OPC UA로 연결").click()
                opcua = register.locator("details").filter(has_text="OPC UA로 연결")
                _fill(
                    opcua,
                    {
                        "연결 ID": "opcua-motor",
                        "연결 이름": "모터 OPC UA",
                        "설비": "motor-01",
                        "OPC UA 서버 주소": endpoint,
                    },
                )
                opcua.get_by_role("button", name="변수 찾기").click()
                opcua.get_by_role("listitem").filter(has_text="Machine").get_by_role(
                    "button", name="안쪽 찾기"
                ).click()
                variable = opcua.get_by_role("listitem").filter(has_text="VibrationX")
                variable.get_by_role("button", name="가져올 변수로 추가").click()
                pw.expect(opcua.get_by_label("채널 ID")).to_have_value("VibrationX")
                opcua.get_by_role("button", name="OPC UA 연결 등록").click()
                pw.expect(
                    opcua.get_by_text("OPC UA 연결 opcua-motor을 등록했습니다")
                ).to_be_visible()
                live = JsonSourceRepository(workspace.source_registry_path).get("opcua-motor")
                assert [m.node_id for m in live.config.node_mappings] == [node_id]

                live_card = page.get_by_role("region", name="등록한 연결").get_by_role(
                    "article", name="모터 OPC UA"
                )
                live_card.get_by_role("button", name="이 연결 사용하기").click()
                live_card.get_by_role("button", name="1회 읽기로 연결 확인").click()
                pw.expect(live_card.get_by_role("status")).to_contain_text(
                    "한 번 읽어 연결을 확인했습니다"
                )
                pw.expect(live_card.get_by_role("button", name="수집 시작 요청")).to_be_visible()

                example = page.get_by_role("region", name="예시로 둘러보기")
                example.get_by_role("button", name="예시 시작").click()
                opened = example.get_by_role("link", name="예시 화면 열기 (새 탭)")
                back = f"http://127.0.0.1:{server.server_port}/web/?page=system"
                pw.expect(opened).to_have_attribute(
                    "href", "http://127.0.0.1:2799/web/?" + urlencode({"return_to": back})
                )
                example.get_by_role("button", name="예시 종료").click()
                example.get_by_role("group", name="예시를 종료할까요?").get_by_role(
                    "button", name="종료하기"
                ).click()
                pw.expect(example.get_by_role("button", name="예시 시작")).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_sample_workspace_says_it_is_an_example(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "sample")
    initialize_operations_workspace(workspace)
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page: Any = browser.new_page(locale="ko-KR")
                page.route(
                    "**/api/v1/session",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "csrf_token": "sample-token-0000000000",
                                "write_scope": "read-only-synthetic-demo",
                                "workspace_kind": "synthetic-demo",
                                "mode": "example",
                                "can_change": False,
                            }
                        ),
                    ),
                )
                back = "http://127.0.0.1:2718/web/?page=system"
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?" + urlencode({"return_to": back})
                )
                notice = page.get_by_text("합성 예시 데이터 · 별도 작업공간 · 보기 전용")
                pw.expect(notice).to_be_visible()
                pw.expect(
                    page.get_by_role("link", name="내 작업공간으로 돌아가기")
                ).to_have_attribute("href", back)
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
