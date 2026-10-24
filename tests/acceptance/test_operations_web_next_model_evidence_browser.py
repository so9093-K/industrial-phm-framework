"""Model AnalysisRun view must not join another binding's source, input or step."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import expect_place


@pytest.mark.parametrize("width", [390, 1024])
def test_model_run_evidence_refuses_changed_input_identity(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "model-run-evidence")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
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
                binding = {
                    "binding_id": "model-binding-a",
                    "package_id": "model-package-a",
                    "source_id": "source-a",
                    "asset_id": "bearing-a",
                    "step_kind": "acquisition-snapshot",
                    "measurement_point_id": None,
                    "recorded_replay": True,
                    "health": "ok",
                    "health_reason": None,
                    "package": {
                        "package_id": "model-package-a",
                        "recipe_id": "rms-score-v1",
                        "output": {"task": "anomaly-score"},
                    },
                    "latest_analyzed": {"position": 3, "state": "analyzed"},
                    "latest_processed": {"position": 4, "state": "skipped"},
                }
                page.route(
                    "**/api/v1/phm/bindings",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "change_seq": 9,
                                "bindings": [binding],
                            }
                        ),
                    ),
                )

                def model_step(position: int):
                    analyzed = position == 3
                    return {
                        "position": position,
                        "step_key": f"acq:{position}",
                        "state": "analyzed" if analyzed else "skipped",
                        "reason": None if analyzed else "sequence warm-up",
                        "analysis_run_id": f"run-{position}",
                        "change_seq": position,
                        "replay": True,
                        "input_reference": {
                            "kind": "acquisition-snapshot",
                            "source_id": "source-a",
                            "asset_id": "bearing-a",
                            "ordinal": position,
                            "sha256": "a" * 64,
                        },
                        "event_start": None,
                        "event_end": None,
                        "processed_at": "2026-10-16T00:00:00Z",
                        "output": {"score": 0.5, "exceeds_threshold": False} if analyzed else {},
                        "features": {"feature.rms": 0.1} if analyzed else None,
                    }

                page.route(
                    "**/api/v1/phm/trace?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "binding_id": "model-binding-a",
                                "limit": 64,
                                "steps": [model_step(3), model_step(4)],
                            }
                        ),
                    ),
                )
                overrides = {"source_id": "source-a", "failed": False, "run_id": "run-3"}

                def result(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["binding_id"] == ["model-binding-a"]
                    position = int(query["position"][0])
                    if overrides["failed"]:
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body=json.dumps({"error": "phm_store_unavailable"}),
                        )
                        return
                    row = model_step(position)
                    row["input_reference"]["source_id"] = overrides["source_id"]
                    if position == 3:
                        row["analysis_run_id"] = overrides["run_id"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "binding_id": "model-binding-a",
                                "step": row,
                            }
                        ),
                    )

                page.route("**/api/v1/phm/result?**", result)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a",
                    wait_until="networkidle",
                )
                pw.expect(page.get_by_role("heading", name="모델 이상 점수")).to_be_visible()
                expect_place(pw, page, "이상 징후", "모델 점수")
                # The stored output is summarized as score and comparison, not recomputed.
                scores = page.get_by_role("group", name="3번째 측정 모델 결과")
                pw.expect(scores).to_contain_text("0.5")
                pw.expect(scores).to_contain_text("기준 이하")
                pw.expect(scores).to_contain_text("기록 없음")  # no stored threshold
                # Identities stay exact but live under the technical details.
                pw.expect(page.get_by_text("run-3", exact=True)).to_be_hidden()
                page.get_by_text("기술 상세").click()
                pw.expect(page.get_by_text("run-3", exact=True)).to_be_visible()
                pw.expect(page.get_by_text("a" * 64, exact=True)).to_be_visible()
                pw.expect(page.get_by_text("모델이 분석하지 않았습니다")).to_be_visible()
                assert "model_binding=model-binding-a" in page.url
                assert "model_position=3" in page.url
                choose = page.get_by_label("측정 선택 (최근 64회)")
                choose.select_option("4")
                pw.expect(
                    page.get_by_role("heading", name="이 측정은 모델 분석에서 제외됐습니다")
                ).to_be_visible()
                assert page.get_by_text("모델 출력 원본").count() == 0
                choose.select_option("3")
                pw.expect(page.get_by_role("group", name="3번째 측정 모델 결과")).to_be_visible()
                overrides["source_id"] = "different-source"
                choose.select_option("4")
                choose.select_option("3")
                pw.expect(
                    page.get_by_role("heading", name="모델 결과를 확인하지 못했습니다")
                ).to_be_visible()
                assert page.get_by_text("run-3", exact=True).count() == 0
                overrides["source_id"] = "source-a"
                overrides["failed"] = True
                page.get_by_role("button", name="다시 확인").click()
                pw.expect(
                    page.get_by_role("heading", name="모델 결과를 확인하지 못했습니다")
                ).to_be_visible()
                assert page.get_by_text("run-3", exact=True).count() == 0
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
