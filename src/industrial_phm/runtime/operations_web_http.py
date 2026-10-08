"""Loopback-only, GET-only transport for the initial Operations Web read contract.

Not yet the production UI entry point. No CORS, mutation routes, authentication
bypass, or file-serving endpoint is exposed. The existing marimo supervisor is
unchanged until packaged static UI and browser acceptance are ready.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_web_read import project_operations_monitor


def create_operations_web_read_server(
    workspace_root: Path, *, port: int = 0
) -> ThreadingHTTPServer:
    """Construct a single-workspace server on 127.0.0.1 without starting a thread.

    The caller owns serve_forever/shutdown. This reference read transport is not
    installed into the current Operations UI child or CLI.
    """
    if not isinstance(workspace_root, Path) or not workspace_root.is_dir():
        raise ValueError("workspace_root must point to an existing workspace directory")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer between 0 and 65535")
    root = workspace_root.resolve()

    class ReadHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: HTTPStatus, code: str) -> None:
            self._send_json(status, {"error": {"code": code}})

        def _allowed(self) -> bool:
            port_value = self.server.server_address[1]
            host = self.headers.get("Host", "")
            permitted = {
                f"127.0.0.1:{port_value}",
                f"localhost:{port_value}",
            }
            origin = self.headers.get("Origin")
            # Host allowlisting prevents DNS-rebinding reads. Origin and
            # Sec-Fetch-Site reject browser cross-site access even to loopback.
            if host not in permitted:
                return False
            if origin is not None and origin not in {f"http://{item}" for item in permitted}:
                return False
            return self.headers.get("Sec-Fetch-Site") != "cross-site"

        def do_GET(self) -> None:
            if not self._allowed():
                self._error(HTTPStatus.FORBIDDEN, "origin_not_allowed")
                return
            if self.path != "/api/v1/monitor":
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            try:
                snapshot = load_operations_app_snapshot(
                    environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)}
                )
                payload = project_operations_monitor(snapshot)
            except (OSError, ValueError):
                # Never return workspace paths, raw exceptions or tracebacks.
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "snapshot_unavailable")
                return
            self._send_json(HTTPStatus.OK, payload)

        def do_POST(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def do_PUT(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def do_DELETE(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def do_OPTIONS(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def log_message(self, format: str, *args: object) -> None:
            # Do not log request URLs containing asset/source identifiers.
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), ReadHandler)
    server.daemon_threads = True
    return server
