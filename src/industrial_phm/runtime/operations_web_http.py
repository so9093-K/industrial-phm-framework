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
from typing import cast
from urllib.parse import parse_qs, urlsplit

from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_read import project_operations_monitor
from industrial_phm.runtime.operations_web_signals import (
    RANGE_DURATIONS,
    project_history_channels,
    project_signal_history,
)


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
            port_value = cast(ThreadingHTTPServer, self.server).server_port
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

        def _history_query(self, *, channels: bool) -> dict[str, object]:
            if len(self.path) > 1600:
                raise ValueError("query too long")
            parts = urlsplit(self.path)
            allowed = {"asset_id"} if channels else {
                "asset_id", "channel_id", "range", "buckets"
            }
            params = parse_qs(
                parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=12
            )
            if not params or set(params) - allowed:
                raise ValueError("unexpected history query")
            asset_ids = params.get("asset_id", ())
            if len(asset_ids) != 1:
                raise ValueError("one asset_id is required")
            asset_id = asset_ids[0]
            self._validate_id(asset_id)
            if channels:
                return {"asset_id": asset_id}
            signal_ids = params.get("channel_id", ())
            if not 1 <= len(signal_ids) <= 6 or len(set(signal_ids)) != len(signal_ids):
                raise ValueError("1 to 6 distinct channel_id values required")
            for signal_id in signal_ids:
                self._validate_id(signal_id)
            presets = params.get("range", ("1h",))
            buckets = params.get("buckets", ("60",))
            if len(presets) != 1 or presets[0] not in RANGE_DURATIONS:
                raise ValueError("unsupported history range")
            if len(buckets) != 1 or not buckets[0].isascii() or not buckets[0].isdigit():
                raise ValueError("invalid buckets")
            bucket_count = int(buckets[0])
            if not 1 <= bucket_count <= 120:
                raise ValueError("buckets out of bounds")
            return {
                "asset_id": asset_id,
                "channel_ids": tuple(signal_ids),
                "range_preset": presets[0],
                "bucket_count": bucket_count,
            }

        @staticmethod
        def _validate_id(identifier: str) -> None:
            if (
                not identifier
                or identifier != identifier.strip()
                or len(identifier) > 128
                or any(ord(char) < 32 or ord(char) == 127 for char in identifier)
            ):
                raise ValueError("invalid identifier")

        def do_GET(self) -> None:
            if not self._allowed():
                self._error(HTTPStatus.FORBIDDEN, "origin_not_allowed")
                return
            parts = urlsplit(self.path)
            if self.path == "/api/v1/monitor":
                query: dict[str, object] = {}
            elif parts.path in {"/api/v1/history/channels", "/api/v1/history/trend"}:
                try:
                    query = self._history_query(
                        channels=parts.path == "/api/v1/history/channels"
                    )
                except ValueError:
                    self._error(HTTPStatus.BAD_REQUEST, "invalid_history_query")
                    return
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            try:
                snapshot = load_operations_app_snapshot(
                    environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)}
                )
                if self.path == "/api/v1/monitor":
                    payload = project_operations_monitor(snapshot)
                elif parts.path == "/api/v1/history/channels":
                    payload = project_history_channels(
                        snapshot, asset_id=cast(str, query["asset_id"])
                    )
                else:
                    payload = project_signal_history(
                        snapshot,
                        asset_id=cast(str, query["asset_id"]),
                        channel_ids=cast(tuple[str, ...], query["channel_ids"]),
                        range_preset=cast(str, query["range_preset"]),
                        bucket_count=cast(int, query["bucket_count"]),
                    )
            except (OperationsReadError, OSError, ValueError, TypeError):
                # No workspace paths, raw exceptions or tracebacks in responses.
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "history_or_snapshot_unavailable")
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
