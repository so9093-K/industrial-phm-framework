"""Review follow-up: recover source scope, show CSV selection, preserve chart gaps."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
def test_source_scope_can_be_cleared_after_switching_to_another_sources_signal(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    base = datetime(2026, 11, 1, tzinfo=UTC)
    for source, channel, count, step in (
        ("a", "current", 600, 60),
        ("a", "temperature", 600, 60),
        ("b", "temperature", 1200, 10),
    ):
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{source}:{channel}:{i}",
                    source_id=source,
                    asset_id="motor",
                    measurement_point_id="bearing",
                    channel_id=channel,
                    source_file=source + ".csv",
                    source_sha256="b" * 64,
                    source_size_bytes=10,
                    sample_index=i,
                    event_at=base
                    + timedelta(seconds=i * step + (21600 if source == "b" and i >= 600 else 0)),
                    value=65.0 if source == "b" and i >= 600 else 40.0,
                )
                for i in range(count)
            ),
            batch_id=source + "-" + channel,
        )
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=asset_list("motor")
                    ),
                )
                page.goto(origin + "/web/?page=assets&monitor_asset=motor")
                card = page.locator(".found > li").first
                pw.expect(card.locator("path.trace")).to_be_visible()
                path = card.locator("path.trace").get_attribute("d")
                assert path.count("M") == 2 and "L" in path
                pw.expect(card.locator("circle.sample")).not_to_have_count(0)
                page.goto(
                    origin
                    + "/web/?"
                    + urlencode(
                        {
                            "page": "assets",
                            "monitor_asset": "motor",
                            "tab": "signals",
                            "monitor_channel": "temperature",
                        }
                    )
                )
                all_signals = page.get_by_role("region", name="측정 신호", exact=True)
                group_b = all_signals.get_by_role("region", name="측정 기록 · b", exact=True)
                group_a = all_signals.get_by_role("region", name="측정 기록 · a", exact=True)
                pw.expect(group_b).to_be_visible()
                group_b.locator('input[type="range"]').focus()
                group_b.locator('input[type="range"]').press("Home")
                group_b.locator('input[type="range"]').press("ArrowRight")
                chosen_b = group_b.locator(".pick")
                compare_href = chosen_b.get_by_role(
                    "link", name="바로 앞 기간과 비교하기", exact=False
                ).get_attribute("href")
                relation_href = chosen_b.get_by_role(
                    "link", name="다른 신호와 관계 보기", exact=False
                ).get_attribute("href")
                for href in (compare_href, relation_href):
                    scope = parse_qs(urlsplit(href).query)
                    assert scope["monitor_source"] == ["b"] and scope["monitor_point"] == [
                        "bearing"
                    ]
                    assert len(scope["monitor_interpretation"][0]) == 64
                own_a = (
                    group_a.locator(".pick")
                    .get_by_role("link", name="바로 앞 기간과 비교하기", exact=False)
                    .get_attribute("href")
                )
                assert parse_qs(urlsplit(own_a).query)["monitor_source"] == ["a"]
                page.goto(origin + compare_href)
                pw.expect(
                    page.get_by_role("region", name="데이터 출처 b", exact=True)
                ).to_be_visible()
                pw.expect(
                    page.get_by_role("region", name="데이터 출처 a", exact=True)
                ).to_have_count(0)
                page.goto(origin + relation_href)
                pw.expect(page.get_by_role("region", name="신호 관계", exact=True)).to_contain_text(
                    "선택한 출처에서는 함께 기록된 신호가 없습니다"
                )
                focus = {
                    "page": "assets",
                    "monitor_asset": "motor",
                    "monitor_channel": "temperature",
                    "monitor_source": "b",
                    "monitor_point": "bearing",
                }
                page.goto(
                    origin + "/web/?" + urlencode({**focus, "tab": "anomaly", "method": "baseline"})
                )
                panel = page.get_by_role("region", name="달라진 구간 찾기", exact=True)
                pw.expect(panel).to_contain_text("분석 대상 · b")
                panel.locator("#departure-channel").select_option("current")
                recover = panel.get_by_role("button", name="이 신호의 다른 기록 보기", exact=True)
                pw.expect(recover).to_be_visible()
                assert parse_qs(urlsplit(page.url).query)["monitor_source"] == ["b"]
                recover.click()
                pw.expect(panel).to_contain_text("분석 대상 · a")
                assert parse_qs(urlsplit(page.url).query)["monitor_channel"] == ["current"]
                page.goto(origin + "/web/?" + urlencode({**focus, "tab": "signals"}))
                signal = page.get_by_role("region", name="측정 신호", exact=True)
                pw.expect(
                    signal.get_by_role("region", name="측정 기록 · b", exact=True)
                ).to_be_visible()
                signal.locator("#history-channel").select_option("current")
                recover = signal.get_by_role("button", name="모든 출처 보기", exact=True)
                pw.expect(recover).to_be_visible()
                recover.click()
                pw.expect(
                    signal.get_by_role("region", name="측정 기록 · a", exact=True)
                ).to_be_visible()
                assert "monitor_source" not in parse_qs(urlsplit(page.url).query)
                page.goto(
                    origin
                    + "/web/?"
                    + urlencode(
                        {
                            **focus,
                            "tab": "change",
                            "method": "relation",
                            "data": "history",
                            "relation_x": "temperature",
                            "relation_y": "current",
                        }
                    )
                )
                relation = page.get_by_role("region", name="신호 관계", exact=True)
                pw.expect(relation).to_contain_text("선택한 출처에서는 함께 기록된 신호가 없습니다")
                pw.expect(relation.locator(".group")).to_have_count(0)
                before = parse_qs(urlsplit(page.url).query)
                relation.get_by_role("button", name="다른 출처의 기록 보기", exact=True).click()
                pw.expect(relation.locator(".group h3")).to_have_text("a / bearing")
                pw.expect(
                    relation.get_by_text(
                        "선택한 출처에서는 함께 기록된 신호가 없습니다", exact=False
                    )
                ).to_have_count(0)
                after = parse_qs(urlsplit(page.url).query)
                for key in ("relation_x", "relation_y", "compare_a", "compare_b"):
                    assert before[key] == after[key]
                assert "monitor_source" not in after
                comparison_periods = {
                    "compare_a": "2026-11-01T00:05:00Z~2026-11-01T00:45:00Z",
                    "compare_b": "2026-11-01T01:00:00Z~2026-11-01T01:30:00Z",
                }
                page.goto(
                    origin
                    + "/web/?"
                    + urlencode(
                        {
                            **focus,
                            "tab": "change",
                            "method": "compare",
                            "data": "history",
                            **comparison_periods,
                        }
                    )
                )
                comparison = page.get_by_role("region", name="두 기간 비교", exact=True)
                pw.expect(
                    comparison.get_by_role("region", name="데이터 출처 b", exact=True)
                ).to_be_visible()
                comparison.locator("details.conditions > summary").click()
                comparison.locator("#compare-channel").select_option("current")
                pw.expect(comparison).to_contain_text("선택한 출처에 비교할 측정이 없습니다")
                before = parse_qs(urlsplit(page.url).query)
                assert before["monitor_source"] == ["b"]
                comparison.get_by_role("button", name="다른 출처의 기록 보기", exact=True).click()
                pw.expect(
                    comparison.get_by_role("region", name="데이터 출처 a", exact=True)
                ).to_be_visible()
                pw.expect(comparison.locator("#compare-channel")).to_have_value("current")
                after = parse_qs(urlsplit(page.url).query)
                for key, period in comparison_periods.items():
                    assert before[key] == after[key] == [period]
                assert "monitor_source" not in after and "monitor_point" not in after
                pw.expect(
                    comparison.get_by_text("선택한 출처에 비교할 측정이 없습니다", exact=False)
                ).to_have_count(0)
                assert not errors
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_csv_shows_excluded_numeric_columns_and_saves_the_revised_selection(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    running = start_web(workspace.root, writer=True)
    names = ["row_id", *[f"signal_{i}" for i in range(1, 14)], "temperature"]
    csv = (
        "timestamp,"
        + ",".join(names)
        + "\n"
        + "\n".join(
            (datetime(2026, 11, 1, tzinfo=UTC) + timedelta(minutes=i)).isoformat()
            + ","
            + ",".join(str(i + n) for n in range(15))
            for i in range(30)
        )
    )
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(f"http://127.0.0.1:{running[0].server_port}/web/?page=system")
                panel = page.get_by_role("region", name="CSV 데이터 등록")
                panel.get_by_label("CSV 파일 (UTF-8 · 20MiB 이하)").set_input_files(
                    {"name": "wide.csv", "mimeType": "text/csv", "buffer": csv.encode()}
                )
                summary = panel.locator(".selection-summary")
                pw.expect(summary).to_contain_text("저장할 측정값 12개 · 제외된 숫자 열 3개")
                pw.expect(summary).to_contain_text("저장 대상: row_id")
                pw.expect(summary.locator(".selection-caution")).to_contain_text("temperature")
                pw.expect(summary.locator(".selection-caution")).to_contain_text(
                    "숫자 열 15개 중 최대 12개"
                )
                detail = (
                    panel.locator("details")
                    .filter(has=page.get_by_text("측정값 상세 설정·통계", exact=True))
                    .first
                )
                assert detail.get_attribute("open") is None
                summary.get_by_role("button", name="저장 대상 확인·변경").click()
                pw.expect(detail.get_by_role("checkbox", name="row_id", exact=True)).to_be_focused()
                detail.get_by_role("checkbox", name="row_id", exact=True).uncheck()
                detail.get_by_role("checkbox", name="temperature", exact=True).check()
                detail.get_by_text("측정값 상세 설정·통계", exact=True).click()
                pw.expect(summary.locator(".selection-caution")).to_contain_text("row_id")
                pw.expect(summary.locator(".selection-caution")).not_to_contain_text("temperature")
                panel.get_by_label("설비 이름·번호").fill("wide-csv")
                panel.get_by_role("button", name="확인하고 저장하기", exact=True).click()
                pw.expect(panel.get_by_role("heading", name="등록 완료", exact=True)).to_be_visible(
                    timeout=60000
                )
                history = DuckLakeAssetHistory(
                    DuckLakeAssetHistoryConfig(
                        workspace.history_catalog_path, workspace.history_data_path
                    )
                )
                stored = history.list_history_channels("wide-csv")
                assert len(stored) == 12 and "temperature" in stored and "row_id" not in stored
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)
