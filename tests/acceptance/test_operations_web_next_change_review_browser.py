"""Major change → exact comparison → judgment → revisit on a growing record."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import phm_workspace
from tests.support.web_next import InProcessSupervisor, asset_list, stop_web


@pytest.mark.parametrize("width", [390, 1280])
def test_change_review_revisit_keeps_source_and_reference(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    base = datetime(2026, 10, 1, tzinfo=UTC)

    def append(source: str, start: int, end: int, changed: bool) -> None:
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{source}:{channel}:{'b' * 64}:{i}",
                    source_id=source,
                    measurement_point_id="bearing",
                    asset_id="motor",
                    channel_id=channel,
                    source_file="s.csv",
                    source_sha256="b" * 64,
                    source_size_bytes=1,
                    sample_index=i if channel == "temperature" else 10000 + i,
                    event_at=base + timedelta(minutes=i),
                    value=1 if changed and i >= 60 else 0,
                )
                for i in range(start, end)
                for channel in ("temperature", "pressure")
            ),
            batch_id=f"{source}-{start}",
        )

    append("source-a", 0, 300, False)
    append("source-b", 0, 120, True)
    client = InProcessSupervisor(workspace.root.resolve())
    server = create_operations_web_read_server(workspace.root.resolve(), command_client=client)  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 844}, locale="ko-KR")
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(
                "**/api/v1/monitor",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=asset_list("motor")
                ),
            )
            url = f"http://127.0.0.1:{server.server_port}/web/?" + urlencode(
                {"page": "assets", "monitor_asset": "motor"}
            )
            page.goto(url)
            card = page.locator(".found > li").first
            pw.expect(card).to_contain_text("일정하던 값이 상승")
            assert card.bounding_box()["y"] < 844
            signal_href = card.get_by_role(
                "link", name="변화 구간 조사", exact=False
            ).get_attribute("href")
            pw.expect(card.locator("svg path.trace")).to_have_count(1)
            compare = card.get_by_role(
                "link", name="기록 처음 30%와 비교 →", include_hidden=True
            ).first.get_attribute("href")
            assert "monitor_source=source-b" in compare and "monitor_point=bearing" in compare
            card.get_by_text("판단·메모", exact=True).click()
            card.get_by_role("radio", name="계속 관찰").check()
            card.get_by_label("메모 (선택)").fill("운전 기록과 비교함")
            card.get_by_role("button", name="판단 저장", exact=True).click()
            pw.expect(card.locator(".events li")).to_have_count(1)
            page.reload()
            card = page.locator(".found > li").first
            card.get_by_text("판단·메모", exact=True).click()
            pw.expect(card).to_contain_text("현재 판단 · 계속 관찰")
            pw.expect(card.get_by_role("button", name="판단 저장", exact=True)).to_have_count(0)
            card.get_by_label("후속 메모").fill("다음 측정에서 다시 확인함")
            card.get_by_role("button", name="메모 추가", exact=True).click()
            pw.expect(card.locator(".events li")).to_have_count(2)
            append("source-b", 120, 180, True)
            page.reload()
            page.get_by_text("저장한 주요 변화 검토", exact=True).click()
            archive = page.locator(".facts-panel > details").filter(
                has=page.get_by_text("저장한 주요 변화 검토", exact=True)
            )
            archive.locator("details > summary").first.click()
            pw.expect(archive).to_contain_text("현재 판단 · 계속 관찰")
            pw.expect(archive).to_contain_text("다음 측정에서 다시 확인함")
            archive.get_by_role("button", name="검토 종료", exact=True).click()
            archive.get_by_role("radio", name="추가 점검 필요").check()
            archive.get_by_role("button", name="종료하기", exact=True).click()
            pw.expect(archive.locator(".events li")).to_have_count(3)
            saved_summary = archive.locator("details > summary").first
            pw.expect(saved_summary).to_contain_text("종료")
            saved_summary.click()
            saved_summary.click()
            pw.expect(archive).to_contain_text("검토가 종료되어")
            pw.expect(archive.locator(".events li")).to_have_count(3)
            pw.expect(archive).to_contain_text("추가 점검 필요")
            pw.expect(archive.get_by_role("button", name="판단 저장", exact=True)).to_have_count(0)
            page.goto(f"http://127.0.0.1:{server.server_port}" + compare)
            pw.expect(page.get_by_role("region", name="데이터 출처 source-b")).to_be_visible()
            pw.expect(page.get_by_role("region", name="데이터 출처 source-a")).to_have_count(0)
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
            page.goto(
                f"http://127.0.0.1:{server.server_port}/web/?"
                + urlencode(
                    {
                        "page": "assets",
                        "monitor_asset": "motor",
                        "tab": "change",
                        "method": "relation",
                        "data": "history",
                    }
                )
            )
            slider = page.locator(".point-picker input").first
            pw.expect(slider).to_be_visible()
            slider.focus()
            slider.press("ArrowRight")
            pw.expect(slider).to_have_value("1")
            page.goto(f"http://127.0.0.1:{server.server_port}" + signal_href)
            pw.expect(page.locator(".series .source-name").first).to_contain_text("source-b")
            departure_href = page.get_by_role(
                "link", name="달라진 구간 찾기 →", exact=True
            ).get_attribute("href")
            outlook_href = page.get_by_role(
                "link", name="기준 도달 전망 →", exact=True
            ).get_attribute("href")
            for href in (departure_href, outlook_href):
                assert "monitor_source=source-b" in href and "monitor_point=bearing" in href
            with page.expect_response("**/api/v1/explore/anomaly?**") as departure:
                page.goto(f"http://127.0.0.1:{server.server_port}" + departure_href)
            assert departure.value.json()["record"]["source_id"] == "source-b"
            with page.expect_response("**/api/v1/forecast?**", timeout=60000) as forecast:
                page.goto(f"http://127.0.0.1:{server.server_port}" + outlook_href)
            forecast_body = forecast.value.json()
            assert forecast_body["source_id"] == "source-b"
            assert forecast_body["measurement_point_id"] == "bearing"
            panel = page.get_by_role("region", name="추세·기준 도달 전망")
            pw.expect(
                panel.get_by_role("heading", name="기록 마지막 시점 기준 전망", exact=True)
            ).to_be_visible(timeout=60000)
            pw.expect(panel.locator(".source-name")).to_contain_text("source-b")
            panel.get_by_text("검토 기록에 남기기 (선택)", exact=True).click()
            panel.get_by_role("radio", name="계속 관찰").check()
            panel.get_by_role("button", name="판단 저장", exact=True).click()
            pw.expect(panel).to_contain_text("현재 판단 · 계속 관찰", timeout=60000)
            page.reload()
            panel.get_by_text("검토 기록에 남기기 (선택)", exact=True).click()
            pw.expect(panel).to_contain_text("현재 판단 · 계속 관찰", timeout=60000)
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
            assert errors == []
            browser.close()
    finally:
        stop_web(server, thread)
        shutil.rmtree(Path(client.socket_path).parent)


def test_partial_model_scores_do_not_turn_the_last_loaded_point_into_latest(tmp_path: Path) -> None:
    from tests.support.phm import analyze, deliver

    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "partial-models")
    for ordinal in range(1, 9):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + ordinal * 0.01)
    analyze(workspace)
    client = InProcessSupervisor(workspace.root.resolve())
    server = create_operations_web_read_server(workspace.root.resolve(), command_client=client)  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="ko-KR")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(
                "**/api/v1/monitor",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=asset_list("bearing-a")
                ),
            )

            def partial(route):
                response = route.fetch()
                body = response.json()
                body["steps"] = body["steps"][:2]
                body["has_more"] = True
                route.fulfill(response=response, json=body)

            page.route("**/api/v1/phm/series?*", partial)
            page.goto(
                f"http://127.0.0.1:{server.server_port}/web/?"
                + urlencode(
                    {
                        "page": "assets",
                        "monitor_asset": "bearing-a",
                        "tab": "anomaly",
                        "method": "model",
                    }
                )
            )
            comparison = page.locator("section.comparison").filter(
                has=page.get_by_role("heading", name="모델별 판단 상태 비교")
            )
            pw.expect(comparison).to_contain_text("일부만 조회")
            pw.expect(comparison).to_contain_text("조회 범위 밖")
            rows = comparison.locator("tbody tr")
            pw.expect(rows).to_have_count(2)
            for index in range(2):
                last = rows.nth(index).locator("td").last
                pw.expect(last).to_contain_text("8번째 측정")
                pw.expect(last).to_contain_text("2번째 측정")
            assert errors == []
            browser.close()
    finally:
        stop_web(server, thread)
        shutil.rmtree(Path(client.socket_path).parent)
