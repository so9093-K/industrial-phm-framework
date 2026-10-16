"""Model AnalysisRun view must not join another binding's source, input or step."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


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
                    base + "/web-next/?view=model-evidence&monitor_asset=bearing-a",
                    wait_until="networkidle",
                )
                pw.expect(
                    page.get_by_role("heading", name="저장 모델 실행과 입력 근거")
                ).to_be_visible()
                pw.expect(page.get_by_text("run-3", exact=True)).to_be_visible()
                pw.expect(page.get_by_text("a" * 64, exact=True)).to_be_visible()
                pw.expect(
                    page.get_by_text("가장 최근 처리 단계와 최근 분석 성공 단계가 다릅니다")
                ).to_be_visible()
                assert "model_binding=model-binding-a" in page.url
                assert "model_position=3" in page.url
                page.get_by_label("모델 실행 회차 (최근 64개 범위)").select_option("4")
                pw.expect(
                    page.get_by_role("heading", name="이 단계는 모델 분석에서 제외됐습니다")
                ).to_be_visible()
                assert page.get_by_text("원본 모델 출력").count() == 0
                page.get_by_label("모델 실행 회차 (최근 64개 범위)").select_option("3")
                pw.expect(page.get_by_text("run-3", exact=True)).to_be_visible()
                overrides["source_id"] = "different-source"
                page.get_by_label("모델 실행 회차 (최근 64개 범위)").select_option("4")
                page.get_by_label("모델 실행 회차 (최근 64개 범위)").select_option("3")
                pw.expect(
                    page.get_by_role("heading", name="모델 근거 일치 검증 실패")
                ).to_be_visible()
                assert page.get_by_text("run-3", exact=True).count() == 0
                overrides["source_id"] = "source-a"
                overrides["failed"] = True
                page.get_by_role("button", name="해당 실행 재조회").click()
                pw.expect(
                    page.get_by_role("heading", name="모델 근거 일치 검증 실패")
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
