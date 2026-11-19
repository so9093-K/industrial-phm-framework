"""A different summary change stays selected through comparison, signal exploration and return."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("kind", ["history", "vibration"])
def test_another_summary_change_survives_analysis_tabs_and_reload(
    tmp_path: Path, kind: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=kind == "vibration")
    asset = "bearing-a" if kind == "vibration" else "pump"
    if kind == "vibration":
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
    else:
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
        )
        for source in ("A", "B"):
            history.append_file_batch(
                tuple(
                    FileBackfillEvent(
                        raw_evidence_id=f"{source}:{channel}:{i}",
                        source_id=source,
                        asset_id=asset,
                        channel_id=channel,
                        source_file=source + ".csv",
                        source_sha256="a" * 64,
                        source_size_bytes=10,
                        sample_index=i,
                        event_at=datetime(2020, 10, 22, tzinfo=UTC) + timedelta(minutes=i),
                        value=after if source == "B" and i >= onset else before,
                        source_metadata_json=json.dumps(
                            {"binding": {"definition": {"unit": unit}}}
                        ),
                    )
                    for channel, before, after, onset, unit in (
                        ("temperature", 40, 65, 60, "°C"),
                        ("pressure", 5, 9, 90, "bar"),
                    )
                    for i in range(120)
                ),
                batch_id=source,
            )
    running = start_web(workspace.root, writer=False)
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
                        body=asset_list(asset), content_type="application/json"
                    ),
                )
                endpoint = "/api/v1/explore/" + ("vibration" if kind == "vibration" else "findings")
                intervals = page.request.get(
                    origin + endpoint + "?" + urlencode({"asset_id": asset})
                ).json()["intervals"]
                assert len(intervals) > 1
                chosen = next(
                    item
                    for item in intervals[1:]
                    if kind == "history" or item["feature"].endswith(".rms")
                )
                page.goto(origin + "/web/?" + urlencode({"page": "assets", "monitor_asset": asset}))
                page.get_by_role(
                    "button",
                    # 진동 특징은 화면에 보이는 쉬운 이름으로 고른다: "수직 진동 크기 (RMS)".
                    name=(
                        chosen["label"]
                        if kind == "history"
                        else chosen["label"].replace(" RMS", " 크기 (RMS)")
                    )
                    + " 변화 크게 보기",
                    exact=True,
                ).click()
                card = page.locator(".found > li").first
                pw.expect(card.get_by_role("heading", level=3)).to_contain_text(
                    chosen["label"] if kind == "history" else chosen["label"].split(" RMS")[0]
                )
                selected = parse_qs(urlsplit(page.url).query, keep_blank_values=True)
                assert selected["summary_kind"] == [kind]
                if kind == "history":
                    assert selected["monitor_source"] == ["B"] and selected["monitor_point"] == [""]
                    assert selected["monitor_channel"] == [chosen["channel"]]
                else:
                    assert selected["feature_b_from"] == [str(chosen["from"])]
                tabs = page.get_by_role("navigation", name="설비 화면")
                tabs.get_by_role("link", name="변화 분석", exact=True).click()
                selector = "#compare-channel" if kind == "history" else "#acquisition-feature"
                pw.expect(page.locator(selector)).to_have_value(
                    chosen["channel"] if kind == "history" else chosen["feature"], timeout=30000
                )
                pw.expect(
                    page.locator(".series" if kind == "history" else ".acquisition .evidence").first
                ).to_be_visible(timeout=30000)
                if kind == "vibration":
                    # The default comparison tab has no explicit method query. An edited
                    # period must still become the relationship screen's current period.
                    assert "method" not in parse_qs(urlsplit(page.url).query)
                    end = chosen["to"] - 1
                    page.locator(".acquisition .ranges fieldset").nth(1).get_by_label(
                        "끝", exact=True
                    ).fill(str(end - 1))  # one-minute intervals, displayed from zero
                    page.get_by_role("button", name="비교하기", exact=True).click()
                    pw.expect(page.locator(".acquisition .evidence")).to_be_visible(timeout=30000)
                    selected["feature_b_to"] = [str(end)]
                compared = parse_qs(urlsplit(page.url).query, keep_blank_values=True)
                for key in (
                    (
                        "compare_a",
                        "compare_b",
                        "monitor_source",
                        "monitor_point",
                        "monitor_interpretation",
                    )
                    if kind == "history"
                    else ("feature_a_from", "feature_a_to", "feature_b_from", "feature_b_to")
                ):
                    assert compared[key] == selected[key]
                page.get_by_role("navigation", name="분석 방법").get_by_role(
                    "link", name="신호 관계", exact=True
                ).click()
                horizontal = (
                    page.locator("#relation-x")
                    if kind == "history"
                    else page.get_by_label("가로축 특징", exact=False)
                )
                pw.expect(horizontal).to_have_value(
                    chosen["channel"] if kind == "history" else chosen["feature"], timeout=30000
                )
                related = parse_qs(urlsplit(page.url).query, keep_blank_values=True)
                if kind == "history":
                    assert related["compare_b"] == selected["compare_b"]
                    assert related["monitor_source"] == ["B"]
                else:
                    assert related["acq_b_from"] == [str(chosen["from"])]
                    assert related["acq_b_to"] == selected["feature_b_to"]
                tabs.get_by_role("link", name="신호", exact=True).click()
                signal_query = parse_qs(urlsplit(page.url).query)
                assert signal_query[
                    "monitor_channel" if kind == "history" else "vibration_feature"
                ] == [chosen["channel"] if kind == "history" else chosen["feature"]]
                tabs.get_by_role("link", name="상태 요약", exact=True).click()
                pw.expect(card.get_by_role("heading", level=3)).to_contain_text(
                    chosen["label"] if kind == "history" else chosen["label"].split(" RMS")[0],
                    timeout=30000,
                )
                page.reload()
                pw.expect(card.get_by_role("heading", level=3)).to_contain_text(
                    chosen["label"] if kind == "history" else chosen["label"].split(" RMS")[0],
                    timeout=30000,
                )
                assert not errors
            finally:
                browser.close()
    finally:
        stop_web(*running)
