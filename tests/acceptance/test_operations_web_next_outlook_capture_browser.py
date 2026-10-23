"""A review request keeps a server-recomputed outlook; the maintenance queue reviews it."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import same_origin

FEATURE = "feature.Horizontal_vibration_signals.rms"
SELECTION_KEYS = {
    "asset_id",
    "kind",
    "series",
    "direction",
    "management_limit",
    "end_limit",
    "changepoint_prior_scale",
    "changepoint_range",
    "seasonality",
    "measurement_version",
    "data_version",
    "source_id",
}


class _InProcessSupervisor:
    """Executes authorized actions the way the supervisor broker does, without IPC."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        return execute_web_source_action(self.root, route, payload)


def _start(root: Path, *, writer: bool) -> tuple[Any, Thread]:
    client = _InProcessSupervisor(root) if writer else None
    server = create_operations_web_read_server(root, command_client=client)  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server: Any, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


def _scale(ordinal: int) -> float:
    return 0.5 + 0.002 * (ordinal % 3) if ordinal <= 40 else 0.5 + 0.06 * (ordinal - 40)


def _asset_list(asset_id: str) -> str:
    return json.dumps(
        {
            "assessed_at": "2026-10-16T00:00:00Z",
            "assets": {
                "items": [
                    {
                        "asset_id": asset_id,
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
    )


def _open(browser: Any, width: int) -> Any:
    """The PHM fixture has no monitored source plan; only the asset list is fixed here.
    Outlook, capture and review requests reach the real server and stores."""
    page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
    page.route(
        "**/api/v1/monitor",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=_asset_list("bearing-a")
        ),
    )
    return page


def _show_optional_review(page: Any) -> None:
    disclosure = page.locator("details.optional-review").first
    if disclosure.get_attribute("open") is None:
        disclosure.locator("summary").click()


@pytest.mark.parametrize("width", [390, 1280])
def test_review_request_queue_restart_and_reobservation_on_stored_acquisitions(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 65):
        deliver(workspace, tmp_path / "waves", ordinal, _scale(ordinal))
    analyze(workspace)
    root = workspace.root.resolve()
    running = [_start(root, writer=True), _start(root, writer=False)]
    writer, viewer = running[0][0], running[1][0]
    outlook_query = "?" + urlencode(
        {
            "page": "assets",
            "tab": "outlook",
            "data": "vibration",
            "monitor_asset": "bearing-a",
            "acq_forecast_feature": FEATURE,
            "acq_management": "2.4",
            "acq_end": "3",
        }
    )
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = _open(browser, width)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                confirmed: list[dict[str, Any]] = []
                page.on(
                    "request",
                    lambda request: (
                        confirmed.append(request.post_data_json)
                        if request.method == "POST" and request.url.endswith("/captures/confirm")
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{writer.server_port}/web/{outlook_query}")
                page.get_by_role("button", name="계산하기", exact=True).click()
                _show_optional_review(page)
                request_button = page.get_by_role("button", name="검토 요청")
                pw.expect(request_button).to_be_enabled(timeout=60000)
                request_button.click()
                pw.expect(page.get_by_text("정비 검토함에 남겼습니다")).to_be_visible(timeout=60000)
                (payload,) = confirmed
                # The browser names the shown selection and provenance, never numbers.
                assert set(payload) == SELECTION_KEYS | {
                    "binding_id",
                    "time_basis",
                    "recorded_period_seconds",
                }
                assert payload["binding_id"] == "anomaly-a"
                assert payload["time_basis"] == "recorded"
                # Repeating the explicit request names the same immutable record.
                request_button.click()
                pw.expect(page.get_by_text("정비 검토함에 남겼습니다")).to_be_visible(timeout=60000)
                assert len(confirmed) == 2
                page.get_by_role("link", name="정비 검토함에서 보기 →").click()

                queue = page.get_by_role("region", name="검토함")
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(page.get_by_role("heading", name="정비 검토", level=1)).to_be_visible()
                pw.expect(
                    queue.get_by_role("link").filter(has_text="검토 요청한 전망")
                ).to_have_count(1, timeout=30000)
                # The saved review keeps the feature ID; people read the feature's name.
                pw.expect(detail.get_by_role("heading", level=2)).to_have_text(
                    "bearing-a · 수평 진동 RMS 전망"
                )
                pw.expect(detail).to_contain_text("추가 측정 4회 후 닿음")
                pw.expect(detail).to_contain_text("원본 데이터: 요청 때와 같음")
                pw.expect(detail).to_contain_text("검토 대기")
                deep_link = page.url.split(str(writer.server_port), 1)[1]
                assert "capture_id=outlook-capture-" in deep_link

                # A session without the supervisor reads the record but cannot act on it.
                observer = _open(browser, width)
                observer.goto(f"http://127.0.0.1:{viewer.server_port}{deep_link}")
                watched = observer.get_by_role("region", name="고른 검토 항목")
                pw.expect(watched).to_contain_text(
                    "보기 전용이라 검토 기록을 남길 수 없습니다", timeout=30000
                )
                pw.expect(watched.get_by_role("textbox")).to_have_count(0)
                pw.expect(watched.get_by_role("button", name="확인함으로 표시")).to_have_count(0)

                # The response to a committed confirmation is lost; the retry reuses its event ID.
                pw.expect(detail.get_by_role("textbox")).to_have_count(0)
                submitted: list[str] = []

                def lost_response(route: Any) -> None:
                    submitted.append(route.request.post_data_json["event_id"])
                    if len(submitted) == 1:
                        committed = route.fetch(headers=same_origin(route))
                        assert committed.status == 200
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body='{"error":{"code":"command_outcome_unknown"}}',
                        )
                    else:
                        route.continue_()

                action_route = "**/api/v1/outlook/captures/review/action"
                page.route(action_route, lost_response)
                # Confirming records the person's decision; it is part of the retried request.
                pw.expect(detail.get_by_role("button", name="확인함으로 표시")).to_be_disabled()
                detail.get_by_role("radio", name="추가 점검 필요").check()
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail).to_contain_text("다시 시도해도 기록이 겹치지 않습니다")
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail.locator(".events li")).to_have_count(1, timeout=30000)
                pw.expect(detail.locator(".badge")).to_have_text("확인함")
                assert len(submitted) == 2 and submitted[0] == submitted[1]
                pw.expect(detail.locator(".events li").first).to_contain_text(
                    "확인 · 추가 점검 필요"
                )
                page.unroute(action_route, lost_response)

                # A second operator closes first; the stale page gets a conflict, not an overwrite.
                other = _open(browser, width)
                other.goto(f"http://127.0.0.1:{writer.server_port}{deep_link}")
                other_detail = other.get_by_role("region", name="고른 검토 항목")
                pw.expect(other_detail.locator(".badge")).to_have_text("확인함", timeout=30000)
                other_detail.get_by_role("button", name="검토 종료").click()
                other_detail.get_by_role("button", name="종료하기").click()
                pw.expect(other_detail.locator(".badge")).to_have_text("검토 종료")
                detail.get_by_role("button", name="검토 종료").click()
                confirm = detail.get_by_role("group", name="검토를 종료할까요?")
                pw.expect(confirm).to_be_focused()
                detail.get_by_role("button", name="종료하기").click()
                pw.expect(detail).to_contain_text("다른 창이나 요청에서 검토 상태가 변경됐습니다")
                pw.expect(detail.locator(".badge")).to_have_text("검토 종료")
                pw.expect(detail.locator(".events li")).to_have_count(2)
                pw.expect(detail.get_by_role("textbox")).to_have_count(0)
                if width == 390:
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth"
                    )
                other.close()
                observer.close()

                # Restart: a new Web process reads the same durable subject and actions.
                _stop(*running.pop(0))
                running.insert(0, _start(root, writer=True))
                writer = running[0][0]
                page.goto(f"http://127.0.0.1:{writer.server_port}{deep_link}")
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail.locator(".badge")).to_have_text("검토 종료", timeout=30000)
                pw.expect(detail.locator(".events li")).to_have_count(2)

                # Later measurements change the projection; the archived result stays as saved.
                for ordinal in range(65, 71):
                    deliver(workspace, tmp_path / "waves", ordinal, _scale(ordinal))
                analyze(workspace)
                page.reload()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail).to_contain_text("원본 데이터: 요청 뒤 바뀜", timeout=30000)
                detail.get_by_role("button", name="지금 데이터로 다시 계산해 비교").click()
                pw.expect(detail).to_contain_text(
                    "새 측정이 들어옴 (64번째 측정 → 70번째 측정)", timeout=60000
                )
                comparison = detail.get_by_role("table").first
                pw.expect(comparison).to_contain_text("관리 기준")
                pw.expect(detail).to_contain_text("추가 측정 4회 후 닿음")
                detail.get_by_role("link", name="설비 화면에서 이 조건으로 다시 보기 →").click()
                page.get_by_role("button", name="계산하기", exact=True).click()
                _show_optional_review(page)
                pw.expect(page.get_by_role("button", name="검토 요청")).to_be_enabled(timeout=60000)
                _show_optional_review(page)
                page.get_by_role("button", name="검토 요청").click()
                pw.expect(page.get_by_text("정비 검토함에 남겼습니다")).to_be_visible(timeout=60000)
                page.get_by_role("link", name="정비 검토함에서 보기 →").click()
                queue = page.get_by_role("region", name="검토함")
                pw.expect(
                    queue.get_by_role("link").filter(has_text="검토 요청한 전망")
                ).to_have_count(2, timeout=30000)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for server, thread in running:
            _stop(server, thread)


def _history_outlook(measurement: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "asset_id": "motor-a",
        "kind": "history",
        "series": "R",
        "axis": "time",
        "measurement_version": measurement,
        "data_version": "b" * 64,
        "source_id": "source-a",
        "measurement_point_id": "point-a",
        "meaning": "remaining-margin-to-user-conditions-not-a-diagnosis",
        "conditions": {"direction": "upper", "management": 12, "end": None},
        "record": {
            "first": "2026-10-15T00:00:00+00:00",
            "last": "2026-10-16T00:00:00+00:00",
            "points": 180,
        },
        "scenarios": [
            {
                "id": "current",
                "limits": {
                    "management": {
                        "state": "expected",
                        "expected": 7200,
                        "earliest": None,
                        "latest": None,
                    }
                },
            }
        ],
        "settings": {
            "changepoint_prior_scale": 0.05,
            "changepoint_range": 0.8,
            "training_points": None,
            "seasonality": "auto",
        },
        "sentences": ["저장된 측정의 변화입니다."],
    }


def test_history_capture_fails_closed_and_separates_read_failure(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "history-capture")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state: dict[str, Any] = {
        "measurement": "a" * 64,
        "writable": True,
        "read_failures": 1,
        "reject": 1,
        "saved": [],
        "posted": [],
    }

    def reply(route: Any, body: dict[str, Any], status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def outlook(route: Any) -> None:
        reply(route, _history_outlook(state["measurement"]))

    def briefings(route: Any) -> None:
        pairs = parse_qs(urlsplit(route.request.url).query)
        selection = urlencode(sorted((key, value[0]) for key, value in pairs.items()))
        reply(route, {"schema_version": 1, "selection": selection, "briefings": []})

    def captures(route: Any) -> None:
        if state["read_failures"]:
            state["read_failures"] -= 1
            reply(route, {"error": "outlook_capture_store_unavailable"}, 503)
            return
        reply(route, {"schema_version": 1, "captures": state["saved"]})

    def confirm(route: Any) -> None:
        body = route.request.post_data_json
        state["posted"].append(body)
        if state["reject"]:
            state["reject"] -= 1
            reply(route, {"error": "invalid_source_action"}, 400)
            return
        outlook = _history_outlook(body["measurement_version"])
        identity = {
            key: outlook.get(key)
            for key in (
                "asset_id",
                "kind",
                "series",
                "source_id",
                "measurement_point_id",
                "axis",
                "time_basis",
                "record",
                "conditions",
                "settings",
                "measurement_version",
                "data_version",
            )
        }
        identity["assumed_period_seconds"] = None
        capture_id = "outlook-capture-" + "c" * 64
        state["saved"] = [
            {
                "capture_id": capture_id,
                "captured_at": "2026-10-16T00:30:00+00:00",
                "snapshot": {
                    "schema_version": 1,
                    "identity": identity,
                    "selection": {},
                    "outlook": outlook,
                    "meaning": "captured-condition-outlook-not-actual-failure-or-maintenance",
                },
                "source_recheck": "same_measurement_projection",
                "review": {"status": "open", "events": []},
            }
        ]
        reply(route, {"schema_version": 1, "capture_id": capture_id, "asset_id": "motor-a"}, 201)

    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=_asset_list("motor-a")
                    ),
                )
                # The asset workspace now reads stored input identity directly, not
                # indirectly from the forecast options endpoint.
                page.route(
                    "**/api/v1/explore/sources?**",
                    lambda route: reply(
                        route,
                        {
                            "schema_version": 1,
                            "asset_id": "motor-a",
                            "history": {"channels": [{"id": "R"}]},
                            "acquisition": None,
                        },
                    ),
                )
                page.route(
                    "**/api/v1/forecast/options?**",
                    lambda route: reply(
                        route,
                        {
                            "schema_version": 1,
                            "asset_id": "motor-a",
                            "history": {
                                "series": [{"key": "R"}],
                                "horizons": {
                                    "1h": None,
                                    "24h": "short-history",
                                    "7d": "short-history",
                                    "30d": "short-history",
                                },
                            },
                        },
                    ),
                )
                page.route(
                    "**/api/v1/forecast?**",
                    lambda route: reply(
                        route,
                        {
                            "schema_version": 1,
                            "asset_id": "motor-a",
                            "kind": "history",
                            "series": "R",
                            "horizon": "1h",
                            "axis": "time",
                            "measurement_version": state["measurement"],
                            "source_id": "source-a",
                            "measurement_point_id": "point-a",
                            "unit": "A",
                            "meaning": "stored-flow-continued-not-failure-time-or-remaining-life",
                            "forecast": [["2026-10-16T01:00:00Z", 11.5, 10.5, 12.5]],
                        },
                    ),
                )
                page.route("**/api/v1/outlook?**", outlook)
                page.route("**/api/v1/outlook/briefings?**", briefings)
                page.route("**/api/v1/outlook/captures?**", captures)
                page.route("**/api/v1/outlook/captures/confirm", confirm)
                page.route(
                    "**/api/v1/session",
                    lambda route: reply(
                        route,
                        {
                            "schema_version": 1,
                            "csrf_token": "correct-supervisor-csrf-token",
                            "can_change": state["writable"],
                            "write_scope": (
                                "supervisor-owned-source-control"
                                if state["writable"]
                                else "read-only-synthetic-demo"
                            ),
                        },
                    ),
                )
                address = (
                    f"http://127.0.0.1:{server.server_port}/web/?page=assets&tab=outlook"
                    "&data=history&monitor_asset=motor-a&monitor_channel=R&projection_management=12"
                )
                page.goto(address)
                calculate = page.get_by_role("button", name="계산하기", exact=True)
                calculate.click()
                _show_optional_review(page)
                request = page.get_by_role("button", name="검토 요청")
                pw.expect(request).to_be_enabled(timeout=15000)
                request.click()
                # The supervisor's recomputation differed: nothing saved, result discarded.
                pw.expect(
                    page.get_by_role("heading", name="데이터가 바뀌어 결과를 다시 계산해야 합니다")
                ).to_be_visible()
                pw.expect(page.locator("main")).to_contain_text("남기지 않았습니다")
                assert page.get_by_role("heading", name="결과", exact=True).count() == 0
                assert state["saved"] == []
                assert set(state["posted"][0]) == SELECTION_KEYS - {"end_limit"}
                assert state["posted"][0]["source_id"] == "source-a"
                assert "binding_id" not in state["posted"][0]

                state["measurement"] = "d" * 64
                calculate.click()
                # A changed result opens as a fresh analysis, with optional capture collapsed.
                _show_optional_review(page)
                request.click()
                pw.expect(page.get_by_text("정비 검토함에 남겼습니다")).to_be_visible(timeout=15000)
                assert state["posted"][1]["measurement_version"] == "d" * 64
                page.get_by_role("link", name="정비 검토함에서 보기 →").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                # One asset's request list failed; that is reported, never shown as empty.
                pw.expect(page.get_by_role("region", name="검토함")).to_contain_text(
                    "검토 항목을 불러오지 못했습니다", timeout=15000
                )
                pw.expect(detail).to_contain_text("마지막 기록 후 약 2.0시간 닿음")

                state["writable"] = False
                page.goto(address)
                calculate.click()
                _show_optional_review(page)
                pw.expect(page.get_by_role("button", name="검토 요청")).to_be_disabled(
                    timeout=15000
                )
                pw.expect(page.locator("main")).to_contain_text(
                    "보기 전용이라 검토를 요청할 수 없습니다"
                )
                assert len(state["posted"]) == 2
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_maintenance_direct_link_requires_matching_asset_and_survives_navigation(
    tmp_path: Path, width: int
) -> None:
    """A cross-asset URL may never pick a capture already loaded in the queue.

    In particular, navigation may not reuse a previous matching ID from B
    while the bookmark still declares asset A as the evidence owner.
    """
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "cross-asset-queue")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ids = {
        asset: "outlook-capture-" + suffix * 64
        for asset, suffix in (("motor-a", "a"), ("motor-b", "b"))
    }

    def record(asset: str) -> dict[str, Any]:
        outlook = {**_history_outlook("a" * 64), "asset_id": asset, "source_id": "source-" + asset}
        identity = {
            key: outlook.get(key)
            for key in (
                "asset_id",
                "kind",
                "series",
                "source_id",
                "measurement_point_id",
                "axis",
                "time_basis",
                "record",
                "conditions",
                "settings",
                "measurement_version",
                "data_version",
            )
        }
        identity["assumed_period_seconds"] = None
        return {
            "capture_id": ids[asset],
            "captured_at": "2026-10-16T00:30:00+00:00",
            "snapshot": {
                "schema_version": 1,
                "identity": identity,
                "selection": {},
                "outlook": outlook,
                "meaning": "captured-condition-outlook-not-actual-failure-or-maintenance",
            },
            "source_recheck": "same_measurement_projection",
            "review": {"status": "open", "events": []},
        }

    def reply(route: Any, data: dict[str, Any], status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(data))

    def captures(route: Any) -> None:
        params = parse_qs(urlsplit(route.request.url).query)
        asset = params["asset_id"][0]
        found = [record(asset)] if asset in ids else []
        requested = params.get("capture_id", [None])[0]
        if requested and requested != ids.get(asset):
            reply(route, {"error": "capture_not_found"}, 404)
            return
        reply(route, {"schema_version": 1, "captures": found})

    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                snapshot = json.loads(_asset_list("motor-a"))
                snapshot["assets"]["items"].append(
                    {
                        "asset_id": "motor-b",
                        "data_flow_status": "stored-history",
                        "last_data_at": None,
                        "attention_count": 0,
                    }
                )
                snapshot["assets"]["total"] = 2
                page.route("**/api/v1/monitor", lambda route: reply(route, snapshot))
                page.route("**/api/v1/outlook/captures?**", captures)

                def reviews(route: Any) -> None:
                    params = parse_qs(urlsplit(route.request.url).query)
                    reply(
                        route,
                        {
                            "schema_version": 1,
                            "asset_id": params["asset_id"][0],
                            "meaning": "human-review-records-not-maintenance-or-diagnosis",
                            "reviews": {"items": [], "total": 0, "truncated": False},
                        },
                    )

                page.route("**/api/v1/reviews?**", reviews)
                base = f"http://127.0.0.1:{server.server_port}"
                wrong = f"/web/?page=maintenance&monitor_asset=motor-a&capture_id={ids['motor-b']}"
                page.goto(base + wrong, wait_until="networkidle")
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail).to_contain_text("검토 항목을 찾을 수 없습니다")
                assert detail.locator("[data-capture-id]").count() == 0

                # A same-page link must not keep the old subject or silently pick B.
                correct = (
                    f"/web/?page=maintenance&monitor_asset=motor-b&capture_id={ids['motor-b']}"
                )
                page.evaluate("(path) => history.pushState({}, '', path)", correct)
                page.evaluate("window.dispatchEvent(new PopStateEvent('popstate'))")
                pw.expect(detail.locator("[data-capture-id]")).to_have_attribute(
                    "data-capture-id", ids["motor-b"]
                )
                page.go_back()
                pw.expect(detail).to_contain_text("검토 항목을 찾을 수 없습니다")
                assert detail.locator("[data-capture-id]").count() == 0

                # The exact correct link and a reload must preserve the same subject.
                page.goto(base + correct, wait_until="networkidle")
                pw.expect(detail.locator("[data-capture-id]")).to_have_attribute(
                    "data-capture-id", ids["motor-b"]
                )
                page.reload(wait_until="networkidle")
                pw.expect(detail.locator("[data-capture-id]")).to_have_attribute(
                    "data-capture-id", ids["motor-b"]
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
