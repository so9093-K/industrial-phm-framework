"""Loopback-only Operations Web preview with narrowly scoped protected actions.

This is not the production UI entry point. Mutations require exact same-origin
browser evidence and a process CSRF token; collection requests do not start
the supervisor or prove ingestion. The existing marimo UI remains unchanged.
"""

from __future__ import annotations

import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Lock
from typing import cast
from urllib.parse import parse_qs, urlsplit

from industrial_phm.application import (
    SourceAlreadyRegisteredError,
    UnknownRegisteredSourceError,
)
from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_actions import (
    WEB_SOURCE_ACTION_ROUTES,
    execute_web_source_action,
)
from industrial_phm.runtime.operations_web_command import (
    WebCommandClient,
    WebCommandOutcomeUnknown,
    WebCommandRejected,
)
from industrial_phm.runtime.operations_web_read import project_operations_monitor
from industrial_phm.runtime.operations_web_setup import (
    SourceControlConflict,
    project_web_source_setup,
)
from industrial_phm.runtime.operations_web_signals import (
    RANGE_DURATIONS,
    project_history_channels,
    project_signal_history,
)
from industrial_phm.runtime.operations_web_writer import WorkspaceWriterBusy, web_workspace_writer


def create_operations_web_read_server(
    workspace_root: Path, *, port: int = 0, command_client: WebCommandClient | None = None
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
    csrf_token = secrets.token_urlsafe(32)
    mutation_lock = Lock()

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

        def _send_asset(self, asset_name: str) -> None:
            """Serve only package-owned frontend files at exact allowlisted routes."""
            mime = {
                "index.html": "text/html; charset=utf-8",
                "app.js": "text/javascript; charset=utf-8",
                "styles.css": "text/css; charset=utf-8",
            }
            if asset_name not in mime:
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            try:
                body = files("industrial_phm.apps").joinpath("web", asset_name).read_bytes()
            except OSError:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "web_asset_unavailable")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime[asset_name])
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; base-uri 'none'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                "form-action 'none'; object-src 'none'",
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
            allowed = {"asset_id"} if channels else {"asset_id", "channel_id", "range", "buckets"}
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
            static_paths = {
                "/web/": "index.html",
                "/web/app.js": "app.js",
                "/web/styles.css": "styles.css",
            }
            if self.path in static_paths:
                self._send_asset(static_paths[self.path])
                return
            parts = urlsplit(self.path)
            if self.path in {"/api/v1/monitor", "/api/v1/sources", "/api/v1/session"}:
                query: dict[str, object] = {}
            elif parts.path in {"/api/v1/history/channels", "/api/v1/history/trend"}:
                try:
                    query = self._history_query(channels=parts.path == "/api/v1/history/channels")
                except ValueError:
                    self._error(HTTPStatus.BAD_REQUEST, "invalid_history_query")
                    return
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            if self.path == "/api/v1/session":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schema_version": 1,
                        "csrf_token": csrf_token,
                        "write_scope": (
                            "supervisor-owned-source-control"
                            if command_client is not None
                            else "local-source-control-and-opcua-preview"
                        ),
                    },
                )
                return
            try:
                snapshot = load_operations_app_snapshot(
                    environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)}
                )
                if self.path == "/api/v1/monitor":
                    payload = project_operations_monitor(snapshot)
                elif self.path == "/api/v1/sources":
                    payload = project_web_source_setup(snapshot)
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
            except OperationsReadError, OSError, ValueError, TypeError:
                # No workspace paths, raw exceptions or tracebacks in responses.
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "history_or_snapshot_unavailable")
                return
            self._send_json(HTTPStatus.OK, payload)

        def do_POST(self) -> None:
            if self.path not in WEB_SOURCE_ACTION_ROUTES:
                self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")
                return
            if not self._allowed():
                self._error(HTTPStatus.FORBIDDEN, "origin_not_allowed")
                return
            host = self.headers.get("Host", "")
            # Mutations require a complete same-origin browser request and
            # a per-server unpredictable token. No wildcard CORS or cookie auth.
            if (
                self.headers.get("Origin") != f"http://{host}"
                or self.headers.get("Sec-Fetch-Site") != "same-origin"
                or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf_token)
            ):
                self._error(HTTPStatus.FORBIDDEN, "write_not_authorized")
                return
            if self.headers.get("Transfer-Encoding") is not None:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_body")
                return
            lengths = self.headers.get_all("Content-Length", ())
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                self._error(HTTPStatus.BAD_REQUEST, "invalid_body")
                return
            length = int(lengths[0])
            if not 1 <= length <= 4096 or self.headers.get("Content-Type") != "application/json":
                self._error(HTTPStatus.BAD_REQUEST, "invalid_body")
                return
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or any(not isinstance(key, str) for key in body):
                    raise ValueError("invalid JSON shape")
                with mutation_lock:
                    if command_client is None:
                        with web_workspace_writer(root):
                            result = execute_web_source_action(root, self.path, body)
                    else:
                        result = command_client.execute(self.path, body)
            except WorkspaceWriterBusy:
                self._error(HTTPStatus.CONFLICT, "workspace_writer_busy")
                return
            except WebCommandRejected as error:
                status_by_code = {
                    "write_not_authorized": HTTPStatus.FORBIDDEN,
                    "source_id_exists": HTTPStatus.CONFLICT,
                    "source_control_conflict": HTTPStatus.CONFLICT,
                    "command_request_conflict": HTTPStatus.CONFLICT,
                    "command_capacity_exceeded": HTTPStatus.SERVICE_UNAVAILABLE,
                    "source_not_found": HTTPStatus.NOT_FOUND,
                    "invalid_source_action": HTTPStatus.BAD_REQUEST,
                }
                self._error(
                    status_by_code.get(error.code, HTTPStatus.SERVICE_UNAVAILABLE), error.code
                )
                return
            except WebCommandOutcomeUnknown:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "command_outcome_unknown")
                return
            except SourceAlreadyRegisteredError:
                self._error(HTTPStatus.CONFLICT, "source_id_exists")
                return
            except SourceControlConflict:
                self._error(HTTPStatus.CONFLICT, "source_control_conflict")
                return
            except UnknownRegisteredSourceError:
                self._error(HTTPStatus.NOT_FOUND, "source_not_found")
                return
            except ValueError, TypeError, UnicodeError, FileNotFoundError, NotADirectoryError:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_source_action")
                return
            except OSError, RuntimeError:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "source_state_unavailable")
                return
            self._send_json(
                (
                    HTTPStatus.CREATED
                    if self.path in {"/api/v1/sources/file", "/api/v1/sources/opcua"}
                    else HTTPStatus.OK
                ),
                result,
            )

        def do_PUT(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def do_DELETE(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def do_OPTIONS(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def do_HEAD(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")

        def log_message(self, format: str, *args: object) -> None:
            # Do not log request URLs containing asset/source identifiers.
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), ReadHandler)
    server.daemon_threads = True
    return server
