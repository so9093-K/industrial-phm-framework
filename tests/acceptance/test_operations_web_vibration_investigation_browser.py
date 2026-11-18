"""One bearing investigation: selected change → answer → comparison → human note → revisit."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.genai import change_answer
from industrial_phm.runtime import operations_web_phm_explanation as explanation_runtime
from tests.support.phm import ScriptedModel, analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


def test_selected_bearing_change_answer_and_judgment_are_one_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace((tmp_path / "ws").resolve())
    for ordinal in range(1, 31):
        deliver(
            workspace,
            tmp_path / "waves",
            ordinal,
            0.5 if ordinal < 16 else 2.0,
            amplitude_unit="g",
            vertical_scale=1.0 if ordinal < 23 else 5.0,
        )
    analyze(workspace)
    summary = "기준보다 높은 진동이 이어져 일시적인 한 측정의 변화로 보기 어렵습니다."
    model = ScriptedModel({"summary": summary, "actions": ["spectrum", "onset"]})
    monkeypatch.setattr(change_answer, "complete_json", model)
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    running = start_web(workspace.root, writer=True)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        body=asset_list("bearing-a"), content_type="application/json"
                    ),
                )
                url = (
                    origin + "/web/?" + urlencode({"page": "assets", "monitor_asset": "bearing-a"})
                )
                page.goto(url)
                panel = page.get_by_role("region", name="선택한 진동 변화 조사")
                ask = panel.get_by_role(
                    "button", name="이 변화는 언제부터 얼마나 이어졌나요?", exact=True
                )
                pw.expect(ask).to_be_enabled()
                assert not model.requests
                assert panel.bounding_box()["y"] < 900
                selected = parse_qs(urlsplit(page.url).query)
                assert selected["summary_kind"] == ["vibration"]
                # Preserve a person's unfinished note when explicitly importing the AI summary.
                review = page.get_by_role("region", name="이 변화를 어떻게 할까요?")
                review.get_by_label("메모 (선택)", exact=True).fill("현장 기록과 대조 중")
                ask.click()
                pw.expect(panel.locator(".answer")).to_have_text(summary, timeout=30000)
                evidence = page.get_by_role("list", name="이 변화를 확인한 근거")
                href = evidence.locator('a[href*="method=spectrum"]').get_attribute("href")
                onset = evidence.locator('a[href*="model_position"]').get_attribute("href")
                query = parse_qs(urlsplit(href).query)
                for part in ("a_from", "a_to", "b_from", "b_to"):
                    assert query["spectrum_" + part] == selected["feature_" + part]
                panel.get_by_role("button", name="판단 메모에 넣기", exact=True).click()
                memo = review.get_by_label("메모 (선택)", exact=True)
                pw.expect(memo).to_have_value(
                    "현장 기록과 대조 중\n\n" + memo.input_value().split("\n\n", 1)[1]
                )
                assert summary in memo.input_value()
                review.get_by_role("radio", name="계속 관찰", exact=True).check()
                review.get_by_role("button", name="판단 저장", exact=True).click()
                pw.expect(review.locator(".events li")).to_have_count(1)
                page.reload()
                pw.expect(review).to_contain_text("현재 판단 · 계속 관찰")
                pw.expect(review.locator(".events li")).to_contain_text(summary)
                assert len(model.requests) == 1
                # The answer's action opens the computed A/B, without silently using another period.
                page.goto(origin + href)
                pw.expect(page.locator(".spectra svg").first).to_be_visible(timeout=30000)
                spectrum_query = parse_qs(urlsplit(page.url).query)
                assert spectrum_query["spectrum_b_from"] == selected["feature_b_from"]
                # The model evidence opens the model result where the change began.
                page.goto(origin + onset)
                assert (
                    parse_qs(urlsplit(page.url).query)["model_position"]
                    == selected["feature_b_from"]
                )
                # This saved change is discoverable without the monitor supplying any assets.
                page.goto(origin + "/web/?page=maintenance")
                page.get_by_role("button", name="전체", exact=True).click()
                pw.expect(page.locator(".items li")).to_have_count(1)
                page.locator(".items a").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail).to_contain_text("현재 판단 · 계속 관찰")
                detail.get_by_label("후속 메모", exact=True).fill("주파수 대역 비교 확인")
                detail.get_by_role("button", name="메모 추가", exact=True).click()
                pw.expect(detail.locator(".events li")).to_have_count(2)
                page.reload()
                pw.expect(detail.locator(".events li")).to_have_count(2)
                assert not errors
            finally:
                browser.close()
    finally:
        stop_web(*running)
