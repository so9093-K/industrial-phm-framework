"""Real estimators, waveforms and read/write APIs through the guided investigation."""

from pathlib import Path

import pytest

from industrial_phm.demo.bearing import prepare_bearing_demo
from tests.support.web_next import start_web, stop_web


@pytest.mark.linux_only
def test_clean_supervised_example_prepares_real_models_and_preserves_parent(tmp_path: Path) -> None:
    import json
    from dataclasses import replace
    from urllib.request import Request, urlopen

    from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
    from industrial_phm.runtime.operations_config import write_operations_runtime_config
    from tests.acceptance.test_operations_web_controlled_journey_browser import _port, _start, _stop

    workspace = OperationsWorkspace(tmp_path / "parent")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=replace(initialized.config.ui, port=port)),
    )
    original = workspace.config_path.read_bytes()
    process = _start(workspace.root, port, tmp_path / "supervisor.log")
    base = f"http://127.0.0.1:{port}"

    def read(url: str):
        with urlopen(url, timeout=100) as response:
            return json.load(response)

    def command(action: str):
        session = read(base + "/api/v1/session")
        request = Request(
            base + "/api/v1/demo/bearing/" + action,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": base,
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": session["csrf_token"],
            },
        )
        return read(request)

    try:
        started = command("start")
        assert started["scenario"] == "bearing"
        session = read(started["url"].split("/web/")[0] + "/api/v1/session")
        assert session["workspace_kind"] == "bearing-demo" and session["can_change"] is True
        assert session["journey"]["last"] == 96 and len(session["journey"]["bindings"]) == 2
        assert command("start") == started
        assert workspace.config_path.read_bytes() == original
        assert not workspace.source_registry_path.exists()
        assert command("stop")["state"] == "stopped"
        assert command("status")["state"] == "stopped"
        assert command("start") == started
        assert command("stop")["state"] == "stopped"
    finally:
        _stop(process, workspace.root)


@pytest.mark.parametrize("width", [390, 1440])
def test_investigation_keeps_evidence_through_eda_and_human_review(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("torch")
    workspace = prepare_bearing_demo(tmp_path / "example")
    server, thread = start_web(workspace.root, writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 950}, locale="ko-KR")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=assets&monitor_asset=demo-bearing-change"
                )
                guide = page.get_by_role("complementary", name="베어링 분석 체험 안내")
                pw.expect(guide.get_by_text("합성 진동 · 실제 모델 계산")).to_be_visible()
                expected = (
                    ("2. 모델 비교", "모델 이상 점수"),
                    ("3. 신호 확인", "진동 측정"),
                    ("4. 두 기간 비교", "진동 특징 두 기간 비교"),
                    ("5. 특징 관계", "진동 특징 관계"),
                    ("6. 주파수 비교", "주파수 분석"),
                    ("7. 판단 남기기", "모델 이상 점수"),
                )
                for label, heading in expected:
                    guide.get_by_role("link", name=f"다음: {label}", exact=True).click()
                    pw.expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
                    if label == "2. 모델 비교":
                        pw.expect(
                            page.get_by_role("region", name="모델별 점수 비교", exact=True)
                        ).to_be_visible()
                        pw.expect(
                            page.get_by_role("region", name="96번째 측정 원본 파형")
                        ).to_be_visible()
                        page.get_by_role("region", name="모델별 점수 비교", exact=True).get_by_role(
                            "button", name="LSTM 오토인코더", exact=False
                        ).click()
                        page.get_by_label("측정 선택 (최근 64회)").select_option("80")
                    if label == "3. 신호 확인":
                        page.get_by_label("진동 특징", exact=False).select_option(
                            "feature.Vertical_vibration_signals.rms"
                        )
                    if label == "4. 두 기간 비교":
                        pw.expect(page.locator("#acquisition-feature")).to_have_value(
                            "feature.Vertical_vibration_signals.rms"
                        )
                    if label == "7. 판단 남기기":
                        assert "model_position=80" in page.url
                        pw.expect(page.locator("#model-review > summary")).to_be_in_viewport()
                        pw.expect(page.locator("#model-review > summary")).to_be_focused()
                    if label in {"4. 두 기간 비교", "5. 특징 관계", "6. 주파수 비교"}:
                        pw.expect(page.locator("main svg").last).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                    assert "monitor_asset=demo-bearing-change" in page.url
                review = page.get_by_role("region", name="사람 검토", exact=True)
                review.get_by_role("button", name="검토 요청", exact=True).click()
                review.get_by_role("link", name="정비 검토함에서 보기").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                detail.get_by_role("radio", name="계속 관찰", exact=True).check()
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail.locator(".badge")).to_have_text("확인함")
                page.reload()
                pw.expect(detail.locator(".badge")).to_have_text("확인함")
                # The example keeps review records but offers no new data or model connections.
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=system&section=connections"
                )
                pw.expect(
                    page.get_by_text("이 체험 작업공간은 준비된 기록만 사용합니다", exact=False)
                ).to_be_visible()
                assert page.get_by_role("button", name="파일 선택").count() == 0
                assert page.get_by_role("region", name="예시로 둘러보기").count() == 0
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=assets"
                    "&monitor_asset=demo-bearing-change&tab=anomaly&method=model"
                )
                pw.expect(page.get_by_role("region", name="모델별 점수 비교")).to_be_visible()
                assert page.get_by_text("다른 모델 연결", exact=False).count() == 0
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
