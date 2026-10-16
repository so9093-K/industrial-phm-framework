"""Loopback-only Operations Web preview with narrowly scoped protected actions.

The same read/HTTP transport serves supervised Web and standalone preview.
Mutations require exact same-origin browser evidence and a process CSRF token;
collection requests do not start the supervisor or prove ingestion.
Supervised writes are brokered by the Operations supervisor.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
from datetime import datetime
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
from industrial_phm.runtime.operations_status import inspect_operations_runtime_status
from industrial_phm.runtime.operations_web_actions import (
    WEB_SOURCE_ACTION_ROUTES,
    WEB_SUPERVISOR_ONLY_ACTION_ROUTES,
    execute_web_source_action,
)
from industrial_phm.runtime.operations_web_capabilities import (
    CAPABILITIES_ROUTE,
    handle_capabilities_read,
)
from industrial_phm.runtime.operations_web_command import (
    WebCommandClient,
    WebCommandOutcomeUnknown,
    WebCommandRejected,
)
from industrial_phm.runtime.operations_web_condition import (
    ConditionSelectionError,
    project_electrical_condition,
)
from industrial_phm.runtime.operations_web_explore import (
    EXPLORE_READ_ROUTES,
    handle_explore_read,
)
from industrial_phm.runtime.operations_web_file_history import read_file_history_jobs
from industrial_phm.runtime.operations_web_forecast import (
    FORECAST_ROUTES,
    handle_forecast_read,
)
from industrial_phm.runtime.operations_web_outlook import OUTLOOK_ROUTE, handle_outlook_read
from industrial_phm.runtime.operations_web_outlook_briefing import (
    BRIEFINGS_ROUTE,
    handle_briefings_read,
)
from industrial_phm.runtime.operations_web_outlook_capture import (
    CAPTURES_ROUTE,
    handle_outlook_captures_read,
)
from industrial_phm.runtime.operations_web_phm import PHM_READ_ROUTES, handle_phm_read
from industrial_phm.runtime.operations_web_read import (
    project_operations_monitor,
    project_operations_runtime_status,
)
from industrial_phm.runtime.operations_web_review import WebReviewConflict, WebReviewNotFound
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
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_WEB_ASSET_MIME = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "example-motor.csv": "text/csv; charset=utf-8",
    "example-invalid.csv": "text/csv; charset=utf-8",
    **dict.fromkeys(
        (
            "app.js",
            "navigation.js",
            "asset-context.js",
            "phm-connect.js",
            "source-card.js",
            "condition.js",
            "phm.js",
            "monitor.js",
            "monitor-signal.js",
            "phm-explanation.js",
            "time.js",
            "monitor-history.js",
            "csv-start.js",
            "web-utils.js",
            "source-management.js",
            "analysis-records.js",
            "system-status.js",
            "synthetic-demo.js",
            "file-registration.js",
            "opcua-registration.js",
            "signal-explore.js",
            "capabilities.js",
            "forecast.js",
            "outlook.js",
            "outlook-captures.js",
            "anomaly-explore.js",
        ),
        "text/javascript; charset=utf-8",
    ),
}

_MAX_WEB_CSV_UPLOAD = 20 * 1024 * 1024
# Base64 of the largest upload plus the bounded JSON setup fields.
_MAX_WEB_CSV_REQUEST = 4 * ((_MAX_WEB_CSV_UPLOAD + 2) // 3) + 8192
_UPLOAD_REQUEST_ROUTES = frozenset(
    {"/api/v1/sources/file/upload", "/api/v1/sources/file/upload/preflight"}
)
_UPLOAD_SETUP_FIELDS = frozenset(
    {
        "source_id",
        "name",
        "asset_id",
        "measurement_point_id",
        "channel_columns",
        "timestamp_column",
    }
)
_UPLOAD_SETUP_OPTIONAL_FIELDS = _UPLOAD_SETUP_FIELDS | {"phase_channels"}


def create_operations_web_read_server(
    workspace_root: Path, *, port: int = 0, command_client: WebCommandClient | None = None
) -> ThreadingHTTPServer:
    """Construct a single-workspace server on 127.0.0.1 without starting a thread.

    The caller owns serve_forever/shutdown. Supervised Web supplies the command
    client; standalone preview retains its narrower write scope.
    """
    if not isinstance(workspace_root, Path) or not workspace_root.is_dir():
        raise ValueError("workspace_root must point to an existing workspace directory")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer between 0 and 65535")
    root = workspace_root.resolve()
    context_path = OperationsWorkspace(root).web_context_path
    try:
        synthetic_demo = (
            not context_path.is_symlink()
            and context_path.stat().st_size <= 4096
            and json.loads(context_path.read_text(encoding="utf-8"))
            == {"schema_version": 1, "kind": "synthetic-demo"}
        )
    except OSError, ValueError:
        synthetic_demo = False
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
            mime = _WEB_ASSET_MIME
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

        def _send_web_next_asset(self, name: str) -> None:
            """Serve only build-manifest-listed, package-owned preview assets."""
            if name != "index.html" and not re.fullmatch(
                r"assets/[A-Za-z0-9_-]+\.(?:js|css)", name
            ):
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            try:
                package = files("industrial_phm.apps").joinpath("web_next")
                manifest = json.loads(
                    package.joinpath("asset-manifest.json").read_text(encoding="utf-8")
                )
                if not isinstance(manifest, list) or name not in manifest:
                    self._error(HTTPStatus.NOT_FOUND, "not_found")
                    return
                body = package.joinpath(*name.split("/")).read_bytes()
            except (OSError, UnicodeError, ValueError):
                # No Node build is needed to run the existing /web/ product.
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            content_type = (
                "text/html; charset=utf-8"
                if name == "index.html"
                else "text/javascript; charset=utf-8"
                if name.endswith(".js")
                else "text/css; charset=utf-8"
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
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
            allowed = (
                {"asset_id"}
                if channels
                else {"asset_id", "channel_id", "range", "buckets", "anchor", "source_id"}
            )
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
            anchors = params.get("anchor", ("now",))
            if len(anchors) != 1 or anchors[0] not in {"now", "latest"}:
                raise ValueError("unsupported time anchor")
            sources = params.get("source_id", ())
            if len(sources) > 1:
                raise ValueError("at most one source_id is supported")
            if sources:
                self._validate_id(sources[0])
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
                "time_anchor": anchors[0],
                "source_id": sources[0] if sources else None,
            }

        def _condition_query(self) -> dict[str, object]:
            parts = urlsplit(self.path)
            if len(self.path) > 1000:
                raise ValueError("condition query too long")
            params = parse_qs(
                parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=8
            )
            allowed = {
                "asset_id",
                "period",
                "source_id",
                "point_id",
                "end_at",
                "reference_start",
                "reference_end",
            }
            if set(params) - allowed or any(len(values) != 1 for values in params.values()):
                raise ValueError("unexpected condition query")
            asset = params.get("asset_id", [""])[0]
            self._validate_id(asset)
            period = params.get("period", ["24h"])[0]
            if period not in {"1h", "6h", "24h"}:
                raise ValueError("unsupported period")
            query: dict[str, object] = {"asset_id": asset, "period": period}
            for key in ("source_id", "point_id"):
                if key in params:
                    value = params[key][0]
                    if value:
                        self._validate_id(value)
                        query[key] = value
            for key in ("end_at", "reference_start", "reference_end"):
                if key in params:
                    timestamp = datetime.fromisoformat(params[key][0])
                    if timestamp.utcoffset() is None:
                        raise ValueError("explicit timezone required")
                    query[key] = timestamp
            if ("reference_start" in query) != ("reference_end" in query):
                raise ValueError("reference start/end required together")
            return query

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
                **{"/web/" + name: name for name in _WEB_ASSET_MIME if name != "index.html"},
            }
            asset_path = "/web/" if urlsplit(self.path).path == "/web/" else self.path
            if asset_path in static_paths:
                self._send_asset(static_paths[asset_path])
                return
            parts = urlsplit(self.path)
            if parts.path == "/web-next/" or parts.path.startswith("/web-next/assets/"):
                relative = (
                    "index.html"
                    if parts.path == "/web-next/"
                    else parts.path.removeprefix("/web-next/")
                )
                self._send_web_next_asset(relative)
                return
            if parts.path in FORECAST_ROUTES:
                status, forecast = handle_forecast_read(
                    OperationsWorkspace(root), parts.path, parts.query
                )
                self._send_json(status, forecast)
                return
            if parts.path == BRIEFINGS_ROUTE:
                status, briefings = handle_briefings_read(OperationsWorkspace(root), parts.query)
                self._send_json(status, briefings)
                return
            if parts.path == CAPTURES_ROUTE:
                status, captures = handle_outlook_captures_read(
                    OperationsWorkspace(root), parts.query
                )
                self._send_json(status, captures)
                return
            if parts.path == OUTLOOK_ROUTE:
                status, outlook = handle_outlook_read(OperationsWorkspace(root), parts.query)
                self._send_json(status, outlook)
                return
            if parts.path == CAPABILITIES_ROUTE:
                status, capabilities = handle_capabilities_read(
                    OperationsWorkspace(root),
                    parts.query,
                    can_ask=command_client is not None and not synthetic_demo,
                )
                self._send_json(status, capabilities)
                return
            if parts.path in EXPLORE_READ_ROUTES:
                status, explore_payload = handle_explore_read(
                    OperationsWorkspace(root), parts.path, parts.query
                )
                self._send_json(status, explore_payload)
                return
            if parts.path in PHM_READ_ROUTES:
                status, phm_payload = handle_phm_read(
                    OperationsWorkspace(root), parts.path, parts.query
                )
                self._send_json(status, phm_payload)
                return
            if self.path in {
                "/api/v1/monitor",
                "/api/v1/sources",
                "/api/v1/session",
                "/api/v1/system/runtime",
            }:
                query: dict[str, object] = {}
            elif parts.path == "/api/v1/condition":
                try:
                    query = self._condition_query()
                except ValueError:
                    self._error(HTTPStatus.BAD_REQUEST, "invalid_condition_query")
                    return
            elif parts.path in {"/api/v1/history/channels", "/api/v1/history/trend"}:
                try:
                    query = self._history_query(channels=parts.path == "/api/v1/history/channels")
                except ValueError:
                    self._error(HTTPStatus.BAD_REQUEST, "invalid_history_query")
                    return
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found")
                return
            if self.path == "/api/v1/system/runtime":
                try:
                    runtime_status = inspect_operations_runtime_status(OperationsWorkspace(root))
                    payload = project_operations_runtime_status(runtime_status)
                except OSError, ValueError, TypeError, RuntimeError:
                    self._error(HTTPStatus.SERVICE_UNAVAILABLE, "runtime_status_unavailable")
                    return
                self._send_json(HTTPStatus.OK, payload)
                return
            if self.path == "/api/v1/session":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schema_version": 1,
                        "csrf_token": csrf_token,
                        "write_scope": (
                            "read-only-synthetic-demo"
                            if synthetic_demo
                            else "supervisor-owned-source-control"
                            if command_client is not None
                            else "local-source-control-and-opcua-preview"
                        ),
                        "workspace_kind": "synthetic-demo" if synthetic_demo else "operations",
                        # One Web: what changes are available follows whether operations
                        # (the supervisor and its command broker) runs behind this server.
                        "mode": "example"
                        if synthetic_demo
                        else "operations"
                        if command_client is not None
                        else "view-only",
                        "can_change": command_client is not None and not synthetic_demo,
                    },
                )
                return
            try:
                snapshot = load_operations_app_snapshot(
                    environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)}
                )
                if self.path == "/api/v1/monitor":
                    payload = project_operations_monitor(snapshot)
                elif parts.path == "/api/v1/condition":
                    payload = project_electrical_condition(
                        snapshot,
                        asset_id=cast(str, query["asset_id"]),
                        period=cast(str, query["period"]),
                        source_id=cast(str | None, query.get("source_id")),
                        point_id=cast(str | None, query.get("point_id")),
                        end_at=cast(datetime | None, query.get("end_at")),
                        reference_start=cast(datetime | None, query.get("reference_start")),
                        reference_end=cast(datetime | None, query.get("reference_end")),
                    )
                elif self.path == "/api/v1/sources":
                    payload = project_web_source_setup(
                        snapshot,
                        file_history_jobs=read_file_history_jobs(OperationsWorkspace(root)),
                    )
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
                        time_anchor=cast(str, query["time_anchor"]),
                        source_id=cast(str | None, query["source_id"]),
                    )
            except ConditionSelectionError:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_condition_selection")
                return
            except OperationsReadError, OSError, ValueError, TypeError:
                # No workspace paths, raw exceptions or tracebacks in responses.
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "history_or_snapshot_unavailable")
                return
            self._send_json(HTTPStatus.OK, payload)

        def do_POST(self) -> None:
            if synthetic_demo:
                self._error(HTTPStatus.FORBIDDEN, "synthetic_demo_read_only")
                return
            if self.path not in WEB_SOURCE_ACTION_ROUTES:
                self._error(HTTPStatus.METHOD_NOT_ALLOWED, "read_only")
                return
            if not self._allowed():
                self._error(HTTPStatus.FORBIDDEN, "origin_not_allowed")
                return
            if self.path in WEB_SUPERVISOR_ONLY_ACTION_ROUTES and command_client is None:
                self._error(HTTPStatus.FORBIDDEN, "supervisor_required")
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
            max_length = _MAX_WEB_CSV_REQUEST if self.path in _UPLOAD_REQUEST_ROUTES else 4096
            if (
                not 1 <= length <= max_length
                or self.headers.get("Content-Type") != "application/json"
            ):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_body")
                return
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or any(not isinstance(key, str) for key in body):
                    raise ValueError("invalid JSON shape")
                with mutation_lock:
                    if self.path in _UPLOAD_REQUEST_ROUTES:
                        assert command_client is not None
                        if set(body) != {"setup", "csv_base64"}:
                            raise ValueError("unexpected upload fields")
                        setup, encoded = body["setup"], body["csv_base64"]
                        if (
                            not isinstance(setup, dict)
                            or set(setup)
                            not in {_UPLOAD_SETUP_FIELDS, _UPLOAD_SETUP_OPTIONAL_FIELDS}
                            or not isinstance(encoded, str)
                            or len(encoded) > 4 * ((_MAX_WEB_CSV_UPLOAD + 2) // 3)
                        ):
                            raise ValueError("invalid bounded upload")
                        try:
                            raw = base64.b64decode(encoded, validate=True)
                        except (binascii.Error, ValueError) as error:
                            raise ValueError("invalid CSV encoding") from error
                        if not 0 < len(raw) <= _MAX_WEB_CSV_UPLOAD:
                            raise ValueError("CSV upload size outside limits")
                        # This ephemeral location belongs to the supervisor broker,
                        # never to a user-provided path or workspace-writer bypass.
                        directory = Path(command_client.socket_path).parent / "uploads"
                        staged_name = secrets.token_hex(16) + ".csv"
                        staged = directory / staged_name
                        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        try:
                            with os.fdopen(fd, "wb") as stream:
                                stream.write(raw)
                            result = command_client.execute(
                                self.path, {**setup, "staged_name": staged_name}
                            )
                        finally:
                            staged.unlink(missing_ok=True)
                    elif command_client is None:
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
                    "review_evidence_not_found": HTTPStatus.NOT_FOUND,
                    "review_state_conflict": HTTPStatus.CONFLICT,
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
            except WebReviewConflict:
                self._error(HTTPStatus.CONFLICT, "review_state_conflict")
                return
            except WebReviewNotFound:
                self._error(HTTPStatus.NOT_FOUND, "review_evidence_not_found")
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
                    if self.path
                    in {
                        "/api/v1/sources/file",
                        "/api/v1/sources/file/upload",
                        "/api/v1/sources/opcua",
                        "/api/v1/reviews/request",
                        "/api/v1/outlook/captures/confirm",
                        "/api/v1/analysis/file",
                        "/api/v1/analysis/phase-file",
                    }
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
