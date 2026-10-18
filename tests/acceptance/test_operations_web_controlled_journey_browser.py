"""Real Chromium and separate processes: Web → supervisor IPC → durable records → restart."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRepository,
)
from industrial_phm.runtime import (
    OperationsComponentKind,
    OperationsSupervisorStateKind,
    OperationsSupervisorStateRepository,
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from industrial_phm.runtime.operations_web_actions import (
    WEB_SOURCE_ACTION_ROUTES,
    WEB_SUPERVISOR_ONLY_ACTION_ROUTES,
)

_RUN = "from industrial_phm.cli import main; raise SystemExit(main())"


def _cmd(*args: str) -> list[str]:
    return [sys.executable, "-c", _RUN, *args]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop(proc: subprocess.Popen[bytes], root: Path) -> None:
    if proc.poll() is not None:
        return
    subprocess.run(_cmd("operations", "stop", str(root)), capture_output=True, timeout=15)
    try:
        proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _start(root: Path, port: int, log: Path) -> subprocess.Popen[bytes]:
    with log.open("wb") as output:
        proc = subprocess.Popen(
            _cmd("operations", "start", str(root)),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    until = time.monotonic() + 55
    while time.monotonic() < until:
        if proc.poll() is not None:
            pytest.fail(f"Web exited early: {log.read_text(errors='replace')[-4000:]}")
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                conn.request("GET", "/api/v1/session", headers={"Host": f"127.0.0.1:{port}"})
                response = conn.getresponse()
                if response.status == 200:
                    response.read()
                    return proc
            finally:
                conn.close()
        except OSError:
            pass
        time.sleep(0.2)
    _stop(proc, root)
    pytest.fail("supervised Web not ready: " + log.read_text(errors="replace")[-4000:])


def _no_overflow(page, width: int) -> None:
    measured = page.evaluate("() => [window.innerWidth, document.documentElement.scrollWidth]")
    assert measured[0] == width and measured[1] <= width + 2, measured


def test_supervised_web_serializes_separate_http_processes_and_recovers(tmp_path: Path) -> None:
    """Real HTTP subprocesses must share one supervisor writer, even across restart."""
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")

    workspace = OperationsWorkspace(tmp_path / "web")
    init = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(init.config, ui=OperationsUiConfig(port=port))
    )
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n"
        "2026-10-01T00:00:01+00:00,220.7,219.2,221.1\n",
        encoding="utf-8",
    )
    registration = {
        "source_id": "race-file",
        "name": "Concurrent FILE",
        "asset_id": "motor-01",
        "measurement_point_id": "panel",
        "file_path": "inputs/phase.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "timestamp_column": "timestamp",
    }

    def request(
        method: str,
        path: str,
        *,
        token: str = "",
        payload: dict[str, object] | None = None,
        origin: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers.update(
                {
                    "Content-Type": "application/json",
                    "Origin": origin if origin is not None else f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "X-CSRF-Token": token,
                }
            )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    # Python's independent HTTP clients do not have the supervisor's IPC token
    # or PID. Only the authenticated Web child may forward their browser requests.
    client_code = """
import json
import sys
import time
from http.client import HTTPConnection
from pathlib import Path

port, token, client_id, ready_dir, release, payload = sys.argv[1:]
Path(ready_dir, client_id).touch()
deadline = time.monotonic() + 25
while not Path(release).exists():
    if time.monotonic() > deadline:
        raise TimeoutError("HTTP client release gate was not opened")
    time.sleep(0.01)
connection = HTTPConnection("127.0.0.1", int(port), timeout=15)
try:
    connection.request(
        "POST", "/api/v1/sources/file", body=payload,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
            "Sec-Fetch-Site": "same-origin",
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    print(json.dumps({"status": response.status, "body": json.loads(response.read())}))
finally:
    connection.close()
"""
    log = tmp_path / "supervisor.log"
    processes: list[subprocess.Popen[bytes]] = []
    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        assert session["write_scope"] == "supervisor-owned-source-control"
        token = session["csrf_token"]
        assert isinstance(token, str)

        # Different OS processes race through real HTTP -> Web child -> PID-bound
        # IPC -> one durable source repository. A thread-only broker test cannot
        # detect failures in this public request boundary.
        ready_dir = tmp_path / "ready"
        ready_dir.mkdir()
        release = tmp_path / "release"
        for index in range(6):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        client_code,
                        str(port),
                        token,
                        str(index),
                        str(ready_dir),
                        str(release),
                        json.dumps(registration),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        deadline = time.monotonic() + 25
        while len(list(ready_dir.iterdir())) != len(processes):
            if any(child.poll() is not None for child in processes):
                pytest.fail("an HTTP client exited before the release gate")
            if time.monotonic() > deadline:
                pytest.fail("separate HTTP clients did not reach the release gate")
            time.sleep(0.02)
        release.touch()
        results = []
        for child in processes:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0, stderr.decode(errors="replace")
            results.append(json.loads(stdout))
        assert sorted(item["status"] for item in results) == [201, 409, 409, 409, 409, 409]
        assert all(
            item["body"]["error"]["code"] == "source_id_exists"
            for item in results
            if item["status"] == 409
        )
        assert JsonSourceRepository(workspace.source_registry_path).get("race-file")
        assert not workspace.history_catalog_path.exists()
        status, sources = request("GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False

        # Neither a forged origin nor a missing/incorrect CSRF token may cause
        # another mutation, even though both requests reach a live HTTP listener.
        for bad_token, bad_origin in (
            ("invalid", None),
            (token, "https://untrusted.example"),
        ):
            status, error = request(
                "POST",
                "/api/v1/sources/file",
                token=bad_token,
                payload={**registration, "source_id": "unauthorized"},
                origin=bad_origin,
            )
            assert status == 403, error
        assert JsonSourceRepository(workspace.source_registry_path).get("race-file")
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
        _stop(proc, workspace.root)

    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
    assert JsonSourceRepository(workspace.source_registry_path).get("race-file")

    # A restarted supervisor must preserve committed data, but its Web CSRF
    # capability is new. Replay of an old mutation is not durable exactly-once.
    proc = _start(workspace.root, port, log)
    try:
        status, new_session = request("GET", "/api/v1/session")
        assert status == 200
        new_token = new_session["csrf_token"]
        assert isinstance(new_token, str) and new_token != token
        status, error = request(
            "POST",
            "/api/v1/sources/file",
            token=token,
            payload={**registration, "source_id": "stale-session"},
        )
        assert status == 403, error
        status, duplicate = request(
            "POST",
            "/api/v1/sources/file",
            token=new_token,
            payload=registration,
        )
        assert status == 409
        assert duplicate["error"]["code"] == "source_id_exists"
        status, sources = request("GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


def test_web_child_sigkill_revokes_old_write_authority_and_preserves_workspace(
    tmp_path: Path,
) -> None:
    """Actual supervised Web SIGKILL must fail closed, then restart from durable state."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "web-kill")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    original_config = workspace.config_path.read_bytes()
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phases.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n",
        encoding="utf-8",
    )
    registration = {
        "source_id": "kill-file",
        "name": "Web failure FILE",
        "asset_id": "motor-01",
        "measurement_point_id": "panel",
        "file_path": "inputs/phases.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "timestamp_column": "timestamp",
    }

    def request(
        method: str,
        route: str,
        *,
        payload: dict[str, object] | None = None,
        csrf: str = "",
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers.update(
                {
                    "Origin": f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf,
                }
            )
        try:
            connection.request(method, route, body=body, headers=headers)
            reply = connection.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            connection.close()

    state_repository = OperationsSupervisorStateRepository(workspace.supervisor_state_path)
    log = tmp_path / "supervisor-kill.log"
    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        csrf = session["csrf_token"]
        assert isinstance(csrf, str)
        assert session["write_scope"] == "supervisor-owned-source-control"
        status, created = request("POST", "/api/v1/sources/file", payload=registration, csrf=csrf)
        assert status == 201 and created["registration_state"] == "registered"
        assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 1
        assert not workspace.history_catalog_path.exists()

        running = state_repository.load()
        assert running is not None
        assert running.state == OperationsSupervisorStateKind.RUNNING
        assert running.supervisor_pid == proc.pid
        ui = next(item for item in running.components if item.kind == OperationsComponentKind.UI)
        assert ui.pid != proc.pid
        # Kill only the PID verified against the active supervisor state.
        # The supervisor must stop its other children and release writer ownership.
        os.kill(ui.pid, signal.SIGKILL)
        assert proc.wait(timeout=35) != 0
        failed = state_repository.load()
        assert failed is not None
        assert failed.state == OperationsSupervisorStateKind.FAILED
        assert failed.supervisor_pid == proc.pid
        assert failed.failure is not None and "ui exited with code" in failed.failure
        killed_ui = next(
            item for item in failed.components if item.kind == OperationsComponentKind.UI
        )
        assert killed_ui.return_code == -signal.SIGKILL
        with pytest.raises(OSError):
            request("GET", "/api/v1/session")
        assert workspace.config_path.read_bytes() == original_config
        assert JsonSourceRepository(workspace.source_registry_path).get("kill-file")
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)

    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        new_csrf = session["csrf_token"]
        assert isinstance(new_csrf, str) and new_csrf != csrf
        status, rejected = request(
            "POST",
            "/api/v1/sources/file",
            payload={**registration, "source_id": "stale-session"},
            csrf=csrf,
        )
        assert status == 403 and rejected == {"error": {"code": "write_not_authorized"}}
        status, duplicate = request(
            "POST", "/api/v1/sources/file", payload=registration, csrf=new_csrf
        )
        assert status == 409
        assert duplicate == {"error": {"code": "source_id_exists"}}
        status, sources = request("GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        row = sources["sources"]["items"][0]
        assert row["source_id"] == "kill-file" and row["receipt_confirmed"] is False
        assert workspace.config_path.read_bytes() == original_config
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]


def test_independent_preview_process_cannot_mutate_supervised_workspace(
    tmp_path: Path,
) -> None:
    """Only the supervisor may write until its real cross-process lease is released."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "supervised-and-preview")
    initialized = initialize_operations_workspace(workspace)
    supervisor_port = _port()
    preview_port = _port()
    while preview_port == supervisor_port:
        preview_port = _port()
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=OperationsUiConfig(port=supervisor_port)),
    )
    original_config = workspace.config_path.read_bytes()
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n",
        encoding="utf-8",
    )
    registration = {
        "source_id": "owner-file",
        "name": "Supervisor FILE",
        "asset_id": "motor-01",
        "measurement_point_id": "panel",
        "file_path": "inputs/phase.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "timestamp_column": "timestamp",
    }

    def request(
        port: int,
        route: str,
        *,
        payload: dict[str, object] | None = None,
        token: str = "",
        origin: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers.update(
                {
                    "Origin": origin if origin is not None else f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "X-CSRF-Token": token,
                    "Content-Type": "application/json",
                }
            )
        try:
            connection.request("POST" if payload is not None else "GET", route, body, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    # The preview has a different PID, HTTP port and CSRF generation from
    # the supervised Web child. It must never borrow the supervisor IPC token.
    preview_script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from industrial_phm.runtime.operations_web_http import create_operations_web_read_server\n"
        "server = create_operations_web_read_server(Path(sys.argv[1]), port=int(sys.argv[2]))\n"
        "server.serve_forever()\n"
    )
    supervisor_log = tmp_path / "supervisor.log"
    preview_log = tmp_path / "preview.log"
    supervisor = _start(workspace.root, supervisor_port, supervisor_log)
    try:
        with preview_log.open("wb") as output:
            preview = subprocess.Popen(
                [sys.executable, "-c", preview_script, str(workspace.root), str(preview_port)],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        try:
            deadline = time.monotonic() + 20
            while True:
                if preview.poll() is not None:
                    pytest.fail(
                        "independent Web preview exited: "
                        + preview_log.read_text(errors="replace")[-4000:]
                    )
                try:
                    preview_status, preview_session = request(preview_port, "/api/v1/session")
                    if preview_status == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    pytest.fail("independent Web preview did not start")
                time.sleep(0.1)
            assert preview_session["write_scope"] == "local-source-control-and-opcua-preview"
            # One Web: the state, not the process, says whether changes are available.
            assert (preview_session["mode"], preview_session["can_change"]) == ("view-only", False)
            preview_csrf = preview_session["csrf_token"]
            assert isinstance(preview_csrf, str)
            status, supervisor_session = request(supervisor_port, "/api/v1/session")
            assert status == 200
            assert supervisor_session["write_scope"] == "supervisor-owned-source-control"
            assert (supervisor_session["mode"], supervisor_session["can_change"]) == (
                "operations",
                True,
            )
            supervisor_csrf = supervisor_session["csrf_token"]
            assert isinstance(supervisor_csrf, str) and supervisor_csrf != preview_csrf

            status, created = request(
                supervisor_port,
                "/api/v1/sources/file",
                payload=registration,
                token=supervisor_csrf,
            )
            assert status == 201 and created["registration_state"] == "registered"
            status, visible = request(preview_port, "/api/v1/sources")
            assert status == 200 and visible["sources"]["total"] == 1

            # Concurrent valid same-origin preview POSTs must fail on the actual
            # supervisor's OS-level workspace lease before reaching any facade.
            routes = sorted(WEB_SOURCE_ACTION_ROUTES - WEB_SUPERVISOR_ONLY_ACTION_ROUTES)
            blocked = {**registration, "source_id": "blocked-preview"}

            def attempt(route: str) -> tuple[str, int, dict[str, object]]:
                status, response = request(preview_port, route, payload=blocked, token=preview_csrf)
                return route, status, response

            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(attempt, routes))
            assert len(responses) == len(routes)
            assert all(
                status == 409 and body == {"error": {"code": "workspace_writer_busy"}}
                for _, status, body in responses
            ), responses
            for route in WEB_SUPERVISOR_ONLY_ACTION_ROUTES:
                status, result = request(preview_port, route, payload={}, token=preview_csrf)
                assert status == 403 and result == {"error": {"code": "supervisor_required"}}
            status, result = request(
                preview_port,
                "/api/v1/sources/file",
                payload=blocked,
                token=supervisor_csrf,
            )
            assert status == 403 and result == {"error": {"code": "write_not_authorized"}}
            status, result = request(
                preview_port,
                "/api/v1/sources/file",
                payload=blocked,
                token=preview_csrf,
                origin="https://untrusted.example",
            )
            assert status == 403 and result == {"error": {"code": "origin_not_allowed"}}

            # Live supervisor writes must still succeed; preview cannot modify
            # either the registry or received/collected history.
            status, created = request(
                supervisor_port,
                "/api/v1/sources/file",
                payload={**registration, "source_id": "owner-file-two"},
                token=supervisor_csrf,
            )
            assert status == 201 and created["registration_state"] == "registered"
            assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 2
            assert not workspace.history_catalog_path.exists()
            assert workspace.config_path.read_bytes() == original_config

            # Release the owner lease before trying the identical preview write.
            # No process restart, permission escalation or stale lock workaround.
            _stop(supervisor, workspace.root)
            assert supervisor.returncode == 0, supervisor_log.read_text(errors="replace")[-4000:]
            assert preview.poll() is None
            status, saved = request(
                preview_port, "/api/v1/sources/file", payload=blocked, token=preview_csrf
            )
            assert status == 201 and saved["registration_state"] == "registered"
            status, visible = request(preview_port, "/api/v1/sources")
            assert status == 200 and visible["sources"]["total"] == 3
            assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 3
            assert not workspace.history_catalog_path.exists()
            assert workspace.config_path.read_bytes() == original_config
        finally:
            if preview.poll() is None:
                preview.terminate()
            preview.wait(timeout=15)
    finally:
        _stop(supervisor, workspace.root)


pytestmark = pytest.mark.linux_only


@pytest.mark.parametrize("width", [390, 1440])
def test_supervised_csv_lost_response_reload_analysis_review_and_restart(
    tmp_path: Path, width: int
) -> None:
    """Every write reaches the real PID-bound broker; reload resumes from durable state."""
    from tests.acceptance.test_operations_web_next_connections_browser import _csv
    from tests.support.web_next import same_origin

    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "csv-journey")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    log = tmp_path / "supervisor.log"
    proc = _start(workspace.root, port, log)
    address = f"http://127.0.0.1:{port}/web/"
    review_url = ""
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors = []
                external = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "request",
                    lambda request: (
                        external.append(request.url)
                        if not request.url.startswith(address.split("/web/")[0] + "/")
                        else None
                    ),
                )
                page.goto(address)
                page.get_by_role("link", name="CSV 파일로 시작").click()
                start = page.get_by_role("region", name="CSV 파일로 시작")
                chosen = {"name": "pump.csv", "mimeType": "text/csv", "buffer": _csv()}
                start.get_by_label("CSV 파일 (UTF-8 · 20MiB 이하)").set_input_files(files=[chosen])
                start.get_by_label("설비 이름·번호").fill("journey-pump")
                start.get_by_role("button", name="서버에서 점검 (저장 안 함)").click()
                pw.expect(start.get_by_text("점검 통과")).to_be_visible()
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()

                def lose(route):
                    response = route.fetch(headers=same_origin(route))
                    assert response.status == 201
                    route.fulfill(status=503, json={"error": {"code": "command_outcome_unknown"}})

                page.route("**/api/v1/sources/file/upload", lose)
                start.get_by_role("button", name="등록하고 이력 저장").click()
                pw.expect(start).to_contain_text("결과 확인 필요")
                registered = JsonSourceRepository(workspace.source_registry_path).list_sources()
                assert len(registered) == 1 and not workspace.history_catalog_path.exists()
                page.unroute("**/api/v1/sources/file/upload")
                page.reload()
                start.get_by_label("CSV 파일 (UTF-8 · 20MiB 이하)").set_input_files(files=[chosen])
                pw.expect(start).to_contain_text("이전 작업 입력 복원")
                pw.expect(start.get_by_label("설비 이름·번호")).to_have_value("journey-pump")
                start.get_by_role("button", name="서버에서 점검 (저장 안 함)").click()
                pw.expect(start).to_contain_text("같은 파일과 설정이 이미 등록")
                start.get_by_role("button", name="등록하고 이력 저장").click()
                pw.expect(start).to_contain_text("저장했습니다", timeout=60_000)
                assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 1
                page.get_by_role("article", name="pump.csv").get_by_role(
                    "button", name="신호 통계 분석"
                ).click()
                pw.expect(page.get_by_role("article", name="pump.csv")).to_contain_text(
                    "분석을 저장했습니다"
                )
                page.get_by_role("link", name="분석 기록에서 보기").click()
                record = page.get_by_role("region", name="분석 결과").get_by_role("article")
                pw.expect(record).to_contain_text("journey-pump")
                record.get_by_role("button", name="검토 요청").click()
                record.get_by_role("link", name="정비 검토함에서 보기").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail).to_contain_text("journey-pump")
                detail.get_by_label("메모 (최대 1000자)").fill(
                    "실제 supervisor IPC와 재시작 후 이력 확인"
                )
                detail.get_by_role("button", name="메모 남기기").click()
                pw.expect(detail).to_contain_text("검토 기록을 남겼습니다")
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail.get_by_role("button", name="검토 종료")).to_be_visible()
                detail.get_by_role("button", name="검토 종료").click()
                detail.get_by_role("button", name="종료하기").click()
                pw.expect(detail.get_by_role("button", name="메모 남기기")).to_have_count(0)
                pw.expect(detail).to_contain_text("검토 종료")
                review_url = page.url
                _no_overflow(page, width)
                assert not errors and not external, (errors, external)
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text()[-4000:]
    (finding,) = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
    events = JsonFindingReviewRepository(workspace.maintenance_review_state_path).list_events()
    assert [event.action.value for event in events] == ["note", "acknowledge", "close"]
    assert all(event.finding_id == finding.finding_id for event in events)
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(review_url)
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail).to_contain_text("실제 supervisor IPC와 재시작 후 이력 확인")
                pw.expect(detail).to_contain_text("검토 종료")
                assert detail.get_by_role("button", name="메모 남기기").count() == 0
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)


@pytest.mark.parametrize("width", [390, 1440])
def test_supervised_web_opcua_browse_live_history_disconnect_and_reconnect(
    tmp_path: Path, width: int
) -> None:
    """Real Web commands, collector-owned live history and an observed OPC UA outage.

    A one-shot Web diagnostic is not continuous collection. The simulator is a
    separate real OPC UA server process, restarted on the *same* endpoint; only
    the supervised collector may commit the resulting history to DuckLake.
    """
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("asyncua")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

    workspace = OperationsWorkspace(tmp_path / "opcua-live-browser")
    initialized = initialize_operations_workspace(workspace)
    web_port, opcua_port = _port(), _port()
    while opcua_port == web_port:
        opcua_port = _port()
    endpoint = f"opc.tcp://127.0.0.1:{opcua_port}/phm-demo/"
    source_id = "browser-live-opcua"
    asset_id = "browser-motor"
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=OperationsUiConfig(port=web_port)),
    )
    simulator_log = tmp_path / "opcua-server.log"
    supervisor_log = tmp_path / "opcua-supervisor.log"

    def simulator_start() -> subprocess.Popen[bytes]:
        log_offset = simulator_log.stat().st_size if simulator_log.exists() else 0
        with simulator_log.open("ab") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tools.opcua.demo",
                    "server",
                    "--endpoint",
                    endpoint,
                    "--profile",
                    "power",
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        until = time.monotonic() + 35
        while time.monotonic() < until:
            if process.poll() is not None:
                pytest.fail(
                    "OPC UA simulator terminated before ready: "
                    + simulator_log.read_text(errors="replace")[-4000:]
                )
            if "Synthetic OPC UA server:" in simulator_log.read_text(errors="replace")[log_offset:]:
                return process
            time.sleep(0.2)
        simulator_stop(process)
        pytest.fail("OPC UA simulator readiness timeout")

    def simulator_stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def until_evidence(name: str, predicate, *, timeout: float = 85.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.4)
        pytest.fail(
            f"Missing {name}\nsimulator:\n"
            + simulator_log.read_text(errors="replace")[-4000:]
            + "\nsupervisor:\n"
            + supervisor_log.read_text(errors="replace")[-4000:]
        )

    def source_row(page):
        response = page.request.get(f"http://127.0.0.1:{web_port}/api/v1/sources")
        assert response.ok, (response.status, response.text()[:500])
        payload = response.json()
        assert payload["schema_version"] == 1
        return next(
            (item for item in payload["sources"]["items"] if item["source_id"] == source_id),
            None,
        )

    def matching_source(page, predicate):
        row = source_row(page)
        return row if row is not None and predicate(row) else None

    def browser_evidence(page, stage: str) -> None:
        if root := os.environ.get("PHM_FIRST_RUN_SCREENSHOTS"):
            target = Path(root)
            target.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target / f"opcua-{width}-{stage}.png"), full_page=True)

    simulator = simulator_start()
    supervisor = None
    try:
        supervisor = _start(workspace.root, web_port, supervisor_log)
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                page.goto(f"http://127.0.0.1:{web_port}/web/?page=system")
                page.get_by_text("OPC UA로 연결", exact=True).click()
                form = (
                    page.get_by_role("region", name="다른 방법으로 연결")
                    .locator("details")
                    .filter(has_text="OPC UA로 연결")
                )
                for label, value in {
                    "연결 ID": source_id,
                    "연결 이름": "Browser live OPC UA",
                    "설비": asset_id,
                    "OPC UA 서버 주소": endpoint,
                }.items():
                    form.get_by_label(label, exact=True).fill(value)
                form.get_by_role("button", name="변수 찾기").click()
                form.get_by_role("listitem").filter(has_text="SyntheticPower").get_by_role(
                    "button", name="안쪽 찾기"
                ).click()
                form.get_by_role("listitem").filter(has_text="active_power").get_by_role(
                    "button", name="가져올 변수로 추가"
                ).click()
                assert source_row(page) is None and not workspace.history_catalog_path.exists()
                form.get_by_role("button", name="OPC UA 연결 등록").click()
                card = page.get_by_role("article", name="Browser live OPC UA")
                card.get_by_role("button", name="이 연결 사용하기").click()
                card.get_by_role("button", name="1회 읽기로 연결 확인").click()
                pw.expect(card).to_contain_text("한 번 읽어 연결을 확인했습니다")
                assert source_row(page)["last_live_history_committed_at"] is None
                card.get_by_role("button", name="수집 시작 요청").click()
                first = until_evidence(
                    "collector live history",
                    lambda: matching_source(
                        page,
                        lambda row: (
                            row["last_live_history_snapshot_id"] is not None
                            and row["last_live_received_at"] is not None
                        ),
                    ),
                )
                first_received = first["last_live_received_at"]
                assert first["last_live_history_snapshot_id"] is not None
                page.get_by_role("button", name="다시 불러오기", exact=True).click()
                pw.expect(card.locator(".badge")).to_have_text("수신 확인됨")
                card.get_by_role("link", name="측정 신호 보기").click()
                pw.expect(page.get_by_role("region", name="측정 신호")).to_contain_text(source_id)
                simulator_stop(simulator)
                until_evidence(
                    "collector-observed disconnect",
                    lambda: matching_source(
                        page,
                        lambda row: (
                            row["opcua_session_last_state"] is not None
                            and str(row["opcua_session_last_state"]).upper() != "CONNECTED"
                        ),
                    ),
                )
                simulator = simulator_start()
                until_evidence(
                    "reconnected live receipt",
                    lambda: matching_source(
                        page,
                        lambda row: (
                            str(row["opcua_session_last_state"]).upper() == "CONNECTED"
                            and row["last_live_received_at"] > first_received
                        ),
                    ),
                )
                page.goto(f"http://127.0.0.1:{web_port}/web/?page=system")
                card.get_by_text("다른 작업").click()
                card.get_by_role("button", name="수집 중지 요청").click()
                card.get_by_role("group", name="수집 중지 요청할까요?", exact=False).get_by_role(
                    "button", name="수집 중지 요청"
                ).click()
                until_evidence(
                    "stopped collection",
                    lambda: matching_source(
                        page, lambda row: row["collection_desired_state"] == "stopped"
                    ),
                )
                history = DuckLakeAssetHistory(
                    DuckLakeAssetHistoryConfig(
                        workspace.history_catalog_path, workspace.history_data_path
                    )
                )
                events = history.query_opcua_events(source_id)
                assert events and all(event.event.asset_id == asset_id for event in events)
                assert len({event.local_delivery_identity for event in events}) == len(events)
                _no_overflow(page, width)
            finally:
                browser.close()
    finally:
        if supervisor is not None:
            _stop(supervisor, workspace.root)
        simulator_stop(simulator)


@pytest.mark.parametrize("width", [390, 1440])
def test_cross_asset_reviews_and_runtime_failure_keep_their_own_evidence(
    tmp_path: Path, width: int
) -> None:
    from industrial_phm.application import SqlitePhaseUnbalanceRepository
    from industrial_phm.application.phase_unbalance import PhaseUnbalanceAnalysis
    from tests.support.window_analysis import phase_unbalance_analysis

    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "cross-asset")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    first = phase_unbalance_analysis()
    second = PhaseUnbalanceAnalysis(
        run=replace(
            first.run,
            analysis_run_id="analysis-other",
            source_id="other-source",
            asset_id="motor-8",
        ),
        evidence=replace(
            first.evidence,
            evidence_id="evidence-other",
            analysis_run_id="analysis-other",
            source_id="other-source",
            input_reference=replace(
                first.evidence.input_reference,
                source_id="other-source",
                asset_id="motor-8",
                window_id="window-other",
            ),
        ),
    )
    store = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    store.record(first)
    store.record(second)
    log = tmp_path / "supervisor.log"
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/web/?page=system&section=status")
                status = page.get_by_role("region", name="실행 상태")
                status.get_by_text("기술 상세", exact=True).click()
                pw.expect(status).to_contain_text(str(proc.pid))
                page.route("**/api/v1/system/runtime", lambda route: route.abort())
                page.get_by_role("button", name="다시 불러오기", exact=True).click()
                pw.expect(status).to_contain_text("실행 상태를 확인하지 못했습니다")
                assert status.get_by_text(str(proc.pid), exact=True).count() == 0
                page.unroute("**/api/v1/system/runtime")
                page.get_by_role("button", name="다시 불러오기", exact=True).click()
                pw.expect(status).to_contain_text("데이터 수집기")
                for run in (first, second):
                    page.goto(
                        f"http://127.0.0.1:{port}/web/?page=investigations&monitor_asset={run.run.asset_id}"
                    )
                    record = page.get_by_role("region", name="분석 결과").get_by_role("article")
                    pw.expect(record).to_contain_text(run.run.asset_id)
                    record.get_by_role("button", name="검토 요청").click()
                    record.get_by_role("link", name="정비 검토함에서 보기").click()
                    detail = page.get_by_role("region", name="고른 검토 항목")
                    pw.expect(detail).to_contain_text(run.run.asset_id)
                    pw.expect(detail).not_to_contain_text(
                        "evidence-other" if run is first else first.evidence.evidence_id
                    )
                _no_overflow(page, width)
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    findings = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
    assert {finding.analysis_run_id for finding in findings} == {
        first.run.analysis_run_id,
        second.run.analysis_run_id,
    }
    assert {finding.evidence_refs for finding in findings} == {
        (first.evidence.evidence_id,),
        (second.evidence.evidence_id,),
    }


def test_model_connection_is_analyzed_by_real_runner_and_following_can_be_pinned(
    tmp_path: Path,
) -> None:
    from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
    from industrial_phm.runtime.operations_config import load_operations_runtime_config
    from tests.support.phm import deliver, phm_workspace

    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "real-model", bind=False)
    deliver(workspace, tmp_path / "waves", 1, 0.5)
    port = _port()
    config = load_operations_runtime_config(workspace.config_path)
    write_operations_runtime_config(
        workspace.config_path, replace(config, ui=OperationsUiConfig(port=port))
    )
    log = tmp_path / "supervisor.log"
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/web/?monitor_asset=bearing-a#anomaly")
                offer = page.get_by_role("region", name="연결할 수 있는 이상 탐지 모델")
                offer.get_by_role("listitem").filter(has_text="synthetic-rms-score-v1").get_by_role(
                    "button"
                ).click()
                pw.expect(page.get_by_role("group", name="측정 순서 #1 모델 결과")).to_be_visible(
                    timeout=30_000
                )
                store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
                (binding,) = store.list_bindings()
                assert store.get_result(binding.binding_id, 1).state.value == "analyzed"
                deliver(workspace, tmp_path / "waves", 2, 3.0)
                pw.expect(page.get_by_role("group", name="측정 순서 #2 모델 결과")).to_contain_text(
                    "기준 초과", timeout=20_000
                )
                selector = page.get_by_label("측정 선택 (최근 64회)")
                selector.select_option("1")
                pw.expect(
                    page.get_by_role("button", name="최신 결과 따라보기", exact=True)
                ).to_be_visible()
                deliver(workspace, tmp_path / "waves", 3, 3.2)
                deadline = time.monotonic() + 25
                while store.get_result(binding.binding_id, 3) is None:
                    assert time.monotonic() < deadline, "runner did not analyze the new input"
                    page.wait_for_timeout(100)
                pw.expect(selector).to_have_value("1")
                page.get_by_role("button", name="최신 결과 따라보기", exact=True).click()
                pw.expect(selector).to_have_value("3", timeout=20_000)
                page.route("**/api/v1/phm/trace?*", lambda route: route.abort())
                pw.expect(
                    page.get_by_text("최신 모델 결과를 다시 읽지 못했습니다", exact=False)
                ).to_be_visible(timeout=15_000)
                assert page.locator("[data-model-position]").count() == 0
                page.unroute("**/api/v1/phm/trace?*")
                pw.expect(page.get_by_role("group", name="측정 순서 #3 모델 결과")).to_be_visible(
                    timeout=15_000
                )
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
