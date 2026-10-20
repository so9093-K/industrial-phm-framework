"""Shared current Operations Web helpers for Chromium acceptance tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from threading import Thread
from typing import Any

from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_file_history import FileHistoryJobs
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


def expect_place(pw: Any, page: Any, tab: str, method: str | None = None) -> None:
    """The asset screen shows the expected task tab (and analysis method) as current."""
    tabs = page.get_by_role("navigation", name="설비 화면")
    pw.expect(tabs.get_by_role("link", name=tab, exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    if method is not None:
        # The choice of methods is shown once the asset's data is known, and only when that
        # data supports more than one.
        pw.expect(page.locator(".workspace-asset[aria-busy='true']")).to_have_count(0)
        methods = page.get_by_role("navigation", name="분석 방법")
        if methods.count():
            pw.expect(methods.get_by_role("link", name=method, exact=True)).to_have_attribute(
                "aria-current", "true"
            )


def choose_asset(page: Any, asset_id: str) -> None:
    """Switch to another asset from the asset screen header."""
    page.get_by_label("다른 설비").select_option(asset_id)


class InProcessSupervisor:
    """Executes authorized actions the way the supervisor broker does, without IPC.

    Like the broker it owns a private upload staging directory next to its socket
    path and runs FILE history writes as background jobs.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        broker = Path(tempfile.mkdtemp(prefix="web-broker-"))
        self.socket_path = str(broker / "web.sock")
        self.upload_directory = broker / "uploads"
        self.upload_directory.mkdir()
        self.file_history = FileHistoryJobs(root)

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        if route == "/api/v1/sources/file/backfill/start":
            return self.file_history.start(payload)
        if route in {"/api/v1/sources/file/upload", "/api/v1/sources/file/upload/preflight"}:
            return execute_web_source_action(
                self.root, route, payload, upload_directory=self.upload_directory
            )
        return execute_web_source_action(self.root, route, payload)


def start_web(root: Path, *, writer: bool) -> tuple[Any, Thread]:
    """A Web server over the real workspace; a writer one forwards writes in process."""
    client = InProcessSupervisor(root) if writer else None
    server = create_operations_web_read_server(root, command_client=client)  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_web(server: Any, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


def asset_list(*asset_ids: str) -> str:
    """A monitor body naming only the assets; every other read reaches the real server."""
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
                    for asset_id in asset_ids
                ],
                "total": len(asset_ids),
                "truncated": False,
            },
            "system_error_scopes": [],
        }
    )


def same_origin(route: Any) -> dict[str, str]:
    """Headers to forward an intercepted write to the real server so it commits.

    Interception happens before Chromium adds Sec-Fetch-Site; the page's own
    same-origin request carries it, and the server requires it for writes.
    """
    return {**route.request.all_headers(), "sec-fetch-site": "same-origin"}
