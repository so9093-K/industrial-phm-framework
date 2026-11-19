"""In-process Operations Web server helpers for HTTP integration tests."""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any

from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


class InProcessSupervisor:
    """Forward OPC UA integration-test commands without a broker process."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        return execute_web_source_action(self.root, route, payload)


def start_web(root: Path) -> tuple[Any, Thread]:
    """A read server over the workspace used by the HTTP integration test."""
    server = create_operations_web_read_server(root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_web(server: Any, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)
