"""Web human review must reference exact persisted analysis and preserve dispositions."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application import (
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_web_review import (
    WebReviewConflict,
    WebReviewNotFound,
    record_web_review_action,
    request_web_analysis_review,
)
from tests.support.window_analysis import phase_unbalance_analysis


def _prepared_workspace(tmp_path: Path):
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    analysis = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    return workspace, analysis


def test_review_request_is_exact_evidence_linked_and_idempotent(tmp_path: Path) -> None:
    workspace, analysis = _prepared_workspace(tmp_path)
    root = workspace.root
    payload = {
        "analysis_run_id": analysis.run.analysis_run_id,
        "evidence_id": analysis.evidence.evidence_id,
    }
    with pytest.raises(WebReviewNotFound):
        request_web_analysis_review(root, {**payload, "evidence_id": "unrelated"})
    with pytest.raises(WebReviewNotFound):
        request_web_analysis_review(root, {**payload, "analysis_run_id": "missing"})
    with pytest.raises(ValueError):
        request_web_analysis_review(root, {**payload, "asset_state": "healthy"})
    assert JsonOperationalFindingRepository(workspace.finding_state_path).list_findings() == ()

    first = execute_web_source_action(root, "/api/v1/reviews/request", payload)
    again = execute_web_source_action(root, "/api/v1/reviews/request", payload)
    assert first == again
    assert first["analysis_run_id"] == payload["analysis_run_id"]
    assert first["evidence_ids"] == [payload["evidence_id"]]
    assert first["meaning"] == "human-review-request-not-maintenance-completion-or-diagnosis"
    findings = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
    assert len(findings) == 1
    assert findings[0].finding_id == first["finding_id"]


def test_web_review_events_preserve_status_and_forbid_invalid_transitions(
    tmp_path: Path,
) -> None:
    workspace, analysis = _prepared_workspace(tmp_path)
    request = request_web_analysis_review(
        workspace.root,
        {
            "analysis_run_id": analysis.run.analysis_run_id,
            "evidence_id": analysis.evidence.evidence_id,
        },
    )
    identity = request["finding_id"]
    assert isinstance(identity, str)

    def action(name: str, note: str = "") -> dict[str, object]:
        return record_web_review_action(
            workspace.root, {"finding_id": identity, "action": name, "note": note}
        )

    with pytest.raises(WebReviewConflict):
        action("close")
    with pytest.raises(ValueError):
        action("note")
    with pytest.raises(ValueError):
        action("note", " " + "x")
    with pytest.raises(ValueError):
        action("note", "x" * 1001)
    with pytest.raises(WebReviewNotFound):
        record_web_review_action(
            workspace.root, {"finding_id": "missing", "action": "note", "note": "check"}
        )
    note = action("note", "Check R/S/T channel mapping")
    assert note["status"] == "open"
    acknowledged = action("acknowledge")
    assert acknowledged["status"] == "acknowledged"
    with pytest.raises(WebReviewConflict):
        action("acknowledge")
    closed = action("close", "Reviewed evidence, not physical maintenance")
    assert closed["status"] == "closed"
    replay = request_web_analysis_review(
        workspace.root,
        {
            "analysis_run_id": analysis.run.analysis_run_id,
            "evidence_id": analysis.evidence.evidence_id,
        },
    )
    assert replay["finding_id"] == identity
    assert replay["status"] == "closed"
    with pytest.raises(WebReviewConflict):
        action("note", "after close")
    events = JsonFindingReviewRepository(workspace.maintenance_review_state_path).list_events()
    assert [event.action.value for event in events] == ["note", "acknowledge", "close"]
    assert len({event.event_id for event in events}) == 3


def test_review_request_http_requires_origin_csrf_and_persists_evidence(tmp_path: Path) -> None:
    workspace, analysis = _prepared_workspace(tmp_path)
    server = create_operations_web_read_server(workspace.root, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    def query(
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        token: str = "",
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {"Host": f"127.0.0.1:{port}"}
        raw = None
        if body is not None:
            headers.update(
                {
                    "Origin": f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "Content-Type": "application/json",
                    "X-CSRF-Token": token,
                }
            )
            raw = json.dumps(body).encode()
        try:
            connection.request(method, path, body=raw, headers=headers)
            reply = connection.getresponse()
            value = json.loads(reply.read())
            assert isinstance(value, dict)
            return reply.status, value
        finally:
            connection.close()

    try:
        status, session = query("GET", "/api/v1/session")
        assert status == HTTPStatus.OK
        token = session["csrf_token"]
        assert isinstance(token, str)
        request = {
            "analysis_run_id": analysis.run.analysis_run_id,
            "evidence_id": analysis.evidence.evidence_id,
        }
        assert query("POST", "/api/v1/reviews/request", body=request)[0] == HTTPStatus.FORBIDDEN
        assert (
            query(
                "POST",
                "/api/v1/reviews/request",
                body={**request, "evidence_id": "bad"},
                token=token,
            )[0]
            == HTTPStatus.NOT_FOUND
        )
        assert JsonOperationalFindingRepository(workspace.finding_state_path).list_findings() == ()
        status, finding = query("POST", "/api/v1/reviews/request", body=request, token=token)
        assert status == HTTPStatus.CREATED
        assert finding["evidence_ids"] == [analysis.evidence.evidence_id]
        found = finding["finding_id"]
        assert isinstance(found, str)
        status, acknowledgement = query(
            "POST",
            "/api/v1/reviews/action",
            body={"finding_id": found, "action": "acknowledge", "note": ""},
            token=token,
        )
        assert status == HTTPStatus.OK
        assert acknowledgement["status"] == "acknowledged"
        assert (
            query(
                "POST",
                "/api/v1/reviews/action",
                body={"finding_id": found, "action": "acknowledge", "note": ""},
                token=token,
            )[0]
            == HTTPStatus.CONFLICT
        )
        status, monitor = query("GET", "/api/v1/monitor")
        assert status == HTTPStatus.OK
        assert monitor["review_requests"]["total"] == 1
        assert monitor["review_requests"]["items"][0]["status"] == "acknowledged"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
