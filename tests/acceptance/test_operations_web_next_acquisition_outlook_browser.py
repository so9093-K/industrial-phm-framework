"""Acquisition forecasts remain ordinal and fail closed on version/binding/time basis drift."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import expect_place


@pytest.mark.parametrize("width", [390, 1024])
@pytest.mark.parametrize("spacing", ["recorded", "assumed", "ordinal"])
def test_acquisition_outlook_does_not_invent_clock_and_blocks_drift(
    tmp_path: Path, width: int, spacing: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "acq-outlook")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 960}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "assessed_at": "2026-10-16T00:00:00Z",
                                "assets": {
                                    "items": [
                                        {
                                            "asset_id": "bearing-a",
                                            "data_flow_status": "stored-history",
                                            "last_data_at": None,
                                            "attention_count": 0,
                                        }
                                    ],
                                    "total": 1,
                                    "truncated": False,
                                },
                                "system_error_scopes": [],
                            }
                        ),
                    ),
                )
                recorded_period = None if spacing == "ordinal" else 60
                page.route(
                    "**/api/v1/forecast/options?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "bearing-a",
                                "history": None,
                                "acquisition": {
                                    "source_id": "wave-source",
                                    "binding_id": "binding-a",
                                    "first": 1,
                                    "last": 64,
                                    "count": 64,
                                    "period_seconds": recorded_period,
                                    "series": [
                                        {
                                            "key": "feature.rms",
                                            "label": "진동 RMS",
                                            "valid_points": 64,
                                            "count_forecast": True,
                                        }
                                    ],
                                },
                            }
                        ),
                    ),
                )
                page.route(
                    "**/api/v1/explore/sources?**",
                    lambda route: route.fulfill(
                        json={
                            "schema_version": 1,
                            "asset_id": "bearing-a",
                            "history": None,
                            "acquisition": {
                                "source_id": "wave-source",
                                "binding_id": "binding-a",
                                "first": 1,
                                "last": 64,
                                "count": 64,
                                "period_seconds": recorded_period,
                                "features": [{"key": "feature.rms", "label": "진동 RMS"}],
                            },
                        }
                    ),
                )
                selected = {
                    "binding": "binding-a",
                    "forecast_version": "a" * 64,
                    "outlook_version": "a" * 64,
                }
                basis = "assumed" if spacing == "assumed" else spacing
                interval = 120 if basis == "assumed" else 60 if basis == "recorded" else 1
                assumed = 120 if basis == "assumed" else None

                def matched_query(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["asset_id"] == ["bearing-a"]
                    assert query["kind"] == ["acquisition"]
                    assert query["series"] == ["feature.rms"]
                    assert query.get("assumed_period_seconds") == (
                        ["120"] if spacing == "assumed" else None
                    )
                    return query

                def base_body(version: str):
                    return {
                        "schema_version": 1,
                        "asset_id": "bearing-a",
                        "kind": "acquisition",
                        "axis": "acquisition",
                        "series": "feature.rms",
                        "source_id": "wave-source",
                        "binding_id": selected["binding"],
                        "measurement_point_id": None,
                        "measurement_version": version,
                        "time_basis": basis,
                        "period_seconds": interval,
                        "recorded_period_seconds": recorded_period,
                        "assumed_period_seconds": assumed,
                    }

                def forecast(route):
                    query = matched_query(route)
                    assert query["horizon"] == ["count"]
                    assert query["horizon_count"] == ["30"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                **base_body(selected["forecast_version"]),
                                "horizon": "count",
                                "horizon_count": 30,
                                "meaning": (
                                    "stored-flow-continued-not-failure-time-or-remaining-life"
                                ),
                                "forecast": [[64, 2.2, 2.0, 2.4], [94, 3.4, 3.2, 3.8]],
                            }
                        ),
                    )

                def outlook(route):
                    query = matched_query(route)
                    assert query["direction"] == ["upper"]
                    assert query["management_limit"] == ["2.4"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                **base_body(selected["outlook_version"]),
                                "offset_unit": "acquisition",
                                "data_version": "b" * 64,
                                "meaning": "remaining-margin-to-user-conditions-not-a-diagnosis",
                                "conditions": {
                                    "direction": "upper",
                                    "management": 2.4,
                                    "end": None,
                                },
                                "record": {"first": 1, "last": 64, "points": 64},
                                "search": {"acquisitions": 31, "until": 95},
                                "settings": {
                                    "changepoint_prior_scale": 0.05,
                                    "changepoint_range": 0.9,
                                    "training_points": None,
                                    "seasonality": "off",
                                },
                                "scenarios": [
                                    {
                                        "id": "linear",
                                        "limits": {
                                            "management": {
                                                "state": "expected",
                                                "expected": 4,
                                                "earliest": None,
                                                "latest": None,
                                            }
                                        },
                                    }
                                ],
                            }
                        ),
                    )

                writable = {"yes": True}
                asked = {"yes": False}

                def session(route):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "can_change": writable["yes"],
                                "write_scope": (
                                    "supervisor-owned-source-control"
                                    if writable["yes"]
                                    else "read-only-synthetic-demo"
                                ),
                                "csrf_token": "supervisor-csrf-token-validated",
                            }
                        ),
                    )

                def canonical(query: str) -> str:
                    return urlencode(
                        sorted((key, values[0]) for key, values in parse_qs(query).items())
                    )

                def saved_briefings(route):
                    selection = canonical(urlsplit(route.request.url).query)
                    pairs = parse_qs(selection)
                    assert pairs["binding_id"] == ["binding-a"]
                    assert pairs["measurement_version"] == ["a" * 64]
                    assert pairs["source_id"] == ["wave-source"]
                    assert pairs["time_basis"] == [basis]
                    assert pairs.get("recorded_period_seconds") == (
                        ["60"] if recorded_period is not None else None
                    )
                    assert pairs.get("assumed_period_seconds") == (
                        ["120"] if spacing == "assumed" else None
                    )
                    assert pairs["seasonality"] == ["off"]
                    rows = []
                    if asked["yes"]:
                        rows = [
                            {
                                "id": "briefing-acq",
                                "status": "complete",
                                "question": "획득 변화 설명",
                                "model": "local",
                                "requested_at": "2026-10-16T00:01:00Z",
                                "finished_at": "2026-10-16T00:02:00Z",
                                "answer": {
                                    "summary": "순번별 저장 근거만 설명합니다.",
                                    "points": [{"text": "회차별 변화", "evidence": ["rate"]}],
                                    "evidence": {
                                        "rate": {
                                            "label": "획득 변화",
                                            "text": "서버 계산한 회차당 변화",
                                        }
                                    },
                                    "checks": {"source": "computed"},
                                },
                            }
                        ]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "selection": selection,
                                "briefings": rows,
                            }
                        ),
                    )

                def ask_briefing(route):
                    assert route.request.headers["x-csrf-token"] == (
                        "supervisor-csrf-token-validated"
                    )
                    payload = route.request.post_data_json
                    assert payload["kind"] == "acquisition"
                    assert payload["binding_id"] == "binding-a"
                    assert payload["source_id"] == "wave-source"
                    assert payload["measurement_version"] == "a" * 64
                    assert payload["time_basis"] == basis
                    assert payload["question"] == "획득 변화 설명"
                    asked["yes"] = True
                    selection = urlencode(
                        sorted((key, value) for key, value in payload.items() if key != "question")
                    )
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "briefing_id": "briefing-acq",
                                "status": "pending",
                                "selection": selection,
                            }
                        ),
                    )

                page.route("**/api/v1/session", session)
                page.route("**/api/v1/outlook/briefings?**", saved_briefings)
                page.route("**/api/v1/outlook/briefings/request", ask_briefing)
                page.route("**/api/v1/forecast?**", forecast)
                page.route("**/api/v1/outlook?**", outlook)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?view=acq-outlook&monitor_asset=bearing-a",
                    wait_until="networkidle",
                )
                pw.expect(page.get_by_role("heading", name="기준 도달 전망")).to_be_visible()
                expect_place(pw, page, "상태 전망")
                if spacing == "assumed":
                    page.get_by_label("측정 간격 가정 (선택 · 초, 1~86400)").fill("120")
                page.get_by_label("관리 기준 (선택)").fill("2.4")
                page.get_by_role("button", name="계산하기", exact=True).click()
                pw.expect(page.get_by_role("heading", name="결과", exact=True)).to_be_visible()
                pw.expect(page.get_by_text("추가 측정 4회 후 닿음").first).to_be_visible()
                ticks = page.locator(".chart .x-axis .ticks span")
                assert ticks.count() >= 2
                labels = ticks.all_text_contents()
                if spacing == "ordinal":
                    assert all(label.startswith("#") for label in labels)
                else:
                    assert all(not label.startswith("#") for label in labels)
                    pw.expect(page.locator(".chart .x-axis")).to_contain_text(
                        "기록 시작 후 경과 시간"
                    )
                # Measurement order is never shown as a clock time.
                page.get_by_text("앞으로 30회 측정의 예측값").click()
                assert page.get_by_role("columnheader", name="측정 #").count() == 1
                assert page.get_by_role("columnheader", name="예측 시각").count() == 0
                page.get_by_text("기술 상세").click()
                pw.expect(page.get_by_text("기준 탐색 31회", exact=False)).to_be_visible()
                if spacing == "ordinal":
                    pw.expect(
                        page.get_by_text("측정 간격 정보 없음", exact=False).first
                    ).to_be_visible()
                elif spacing == "assumed":
                    pw.expect(
                        page.get_by_text("가정한 측정 간격", exact=False).first
                    ).to_be_visible()
                else:
                    pw.expect(
                        page.get_by_text("기록된 측정 간격", exact=False).first
                    ).to_be_visible()
                assert "acq_forecast_count=30" in page.url
                ai = page.get_by_role("region", name="AI 해설")
                pw.expect(ai.get_by_role("heading", name="AI 해설")).to_be_visible()
                pw.expect(ai.get_by_role("button", name="해설 만들기")).to_be_enabled()
                ai.get_by_text("직접 질문하기").click()
                ai.get_by_label("AI에게 물을 질문 (최대 600자)").fill("획득 변화 설명")
                ai.get_by_role("button", name="질문 보내기").click()
                pw.expect(page.get_by_text("순번별 저장 근거만 설명합니다.")).to_be_visible()
                assert asked["yes"]
                # Even if the observed version is unchanged, a different
                # binding cannot inherit the prior result.
                selected["binding"] = "binding-changed"
                ai.get_by_role("button", name="해설 다시 확인").click()
                changed = page.get_by_role(
                    "heading", name="데이터가 바뀌어 결과를 다시 계산해야 합니다"
                )
                pw.expect(changed).to_be_visible()
                assert page.get_by_text("순번별 저장 근거만 설명합니다.").count() == 0
                page.get_by_role("button", name="계산하기", exact=True).click()
                pw.expect(changed).to_be_visible()
                assert page.get_by_role("heading", name="결과", exact=True).count() == 0
                selected["binding"] = "binding-a"
                selected["outlook_version"] = "c" * 64
                page.get_by_role("button", name="진동 특징 목록 다시 불러오기").click()
                page.get_by_role("button", name="계산하기", exact=True).click()
                pw.expect(changed).to_be_visible()
                # Read-only mode still shows the numbers but never offers an AI write.
                if width == 390 and spacing == "ordinal":
                    selected["outlook_version"] = "a" * 64
                    writable["yes"] = False
                    asked["yes"] = False
                    page.reload(wait_until="networkidle")
                    page.get_by_label("관리 기준 (선택)").fill("2.4")
                    page.get_by_role("button", name="계산하기", exact=True).click()
                    ai = page.get_by_role("region", name="AI 해설")
                    pw.expect(ai).to_contain_text("보기 전용이라 해설을 만들 수 없습니다")
                    assert ai.get_by_role("button", name="해설 만들기").count() == 0
                    ai.get_by_text("직접 질문하기").click()
                    pw.expect(ai.get_by_role("button", name="질문 보내기")).to_be_disabled()
                    assert not asked["yes"]
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
