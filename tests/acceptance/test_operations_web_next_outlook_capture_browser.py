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
                page.goto(f"http://127.0.0.1:{writer.server_port}/web-next/{outlook_query}")
                page.get_by_role("button", name="계산하기", exact=True).click()
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
                pw.expect(detail.get_by_role("heading", level=2)).to_have_text(
                    f"bearing-a · {FEATURE} 전망"
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
                pw.expect(watched.get_by_role("button", name="메모 남기기")).to_have_count(0)

                # The response to a committed note is lost; the retry reuses its event ID.
                detail.get_by_label("메모").fill("모델 입력과 기준 확인")
                submitted: list[str] = []

                def lost_response(route: Any) -> None:
                    submitted.append(route.request.post_data_json["event_id"])
                    if len(submitted) == 1:
                        committed = route.fetch(headers=same_origin(route))
                        assert committed.status == 200
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body='{"error":"command_outcome_unknown"}',
                        )
                    else:
                        route.continue_()

                action_route = "**/api/v1/outlook/captures/review/action"
                page.route(action_route, lost_response)
                detail.get_by_role("button", name="메모 남기기").click()
                pw.expect(detail).to_contain_text("다시 시도해도 기록이 겹치지 않습니다")
                detail.get_by_role("button", name="메모 남기기").click()
                pw.expect(detail.locator(".events li")).to_have_count(1, timeout=30000)
                pw.expect(detail.locator(".events")).to_contain_text("모델 입력과 기준 확인")
                assert len(submitted) == 2 and submitted[0] == submitted[1]
                page.unroute(action_route, lost_response)

                # A second operator acknowledges first; the stale page gets a conflict.
                other = _open(browser, width)
                other.goto(f"http://127.0.0.1:{writer.server_port}{deep_link}")
                other_detail = other.get_by_role("region", name="고른 검토 항목")
                pw.expect(other_detail).to_contain_text("모델 입력과 기준 확인", timeout=30000)
                other_detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(other_detail.locator(".badge")).to_have_text("확인함")
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail).to_contain_text("다른 사람이 먼저 검토 상태를 바꿨습니다")
                pw.expect(detail.locator(".badge")).to_have_text("확인함")
                pw.expect(detail.locator(".events li")).to_have_count(2)

                detail.get_by_role("button", name="검토 종료").click()
                confirm = detail.get_by_role("group", name="검토를 종료할까요?")
                pw.expect(confirm).to_be_focused()
                detail.get_by_role("button", name="종료하기").click()
                pw.expect(detail.locator(".badge")).to_have_text("검토 종료")
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
                pw.expect(detail.locator(".events li")).to_have_count(3)

                # Later measurements change the projection; the archived result stays as saved.
                for ordinal in range(65, 71):
                    deliver(workspace, tmp_path / "waves", ordinal, _scale(ordinal))
                analyze(workspace)
                page.reload()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail).to_contain_text("원본 데이터: 요청 뒤 바뀜", timeout=30000)
                detail.get_by_role("button", name="지금 데이터로 다시 계산해 비교").click()
                pw.expect(detail).to_contain_text(
                    "새 측정이 들어옴 (측정 순서 #64 → 측정 순서 #70)", timeout=60000
                )
                comparison = detail.get_by_role("table").first
                pw.expect(comparison).to_contain_text("관리 기준")
                pw.expect(detail).to_contain_text("추가 측정 4회 후 닿음")
                detail.get_by_role("link", name="설비 화면에서 이 조건으로 다시 보기 →").click()
                page.get_by_role("button", name="계산하기", exact=True).click()
                pw.expect(page.get_by_role("button", name="검토 요청")).to_be_enabled(timeout=60000)
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
                    f"http://127.0.0.1:{server.server_port}/web-next/?page=assets&tab=outlook"
                    "&data=history&monitor_asset=motor-a&monitor_channel=R&projection_management=12"
                )
                page.goto(address)
                calculate = page.get_by_role("button", name="계산하기", exact=True)
                calculate.click()
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
