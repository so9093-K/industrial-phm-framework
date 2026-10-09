"""Bounded local IPC for a future supervisor-owned Operations Web writer.

Only an active supervisor holding the workspace lifetime lease may host this
broker. Creating a broker grants no HTTP or UI write permission by itself.
The token, peer process identity and allowlisted source action are all required.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import socketserver
import struct
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from industrial_phm.application import (
    SourceAlreadyRegisteredError,
    UnknownRegisteredSourceError,
)
from industrial_phm.runtime.operations_web_actions import (
    WEB_SOURCE_ACTION_ROUTES,
    execute_web_source_action,
)
from industrial_phm.runtime.operations_web_setup import SourceControlConflict

_MAX_MESSAGE_BYTES = 8192
_MAX_REQUESTS_PER_GENERATION = 512
_TIMEOUT_SECONDS = 5.0


class WebCommandRejected(RuntimeError):
    """A bounded, safe-to-display failure returned by the supervisor broker."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WebCommandOutcomeUnknown(RuntimeError):
    """Transport failed; the mutation may have happened, so never retry implicitly."""


class WebCommandClient:
    """Client capability passed only to the intended supervised Web child."""

    def __init__(self, socket_path: str, token: str) -> None:
        self.socket_path = socket_path
        self._token = token

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        if route not in WEB_SOURCE_ACTION_ROUTES:
            raise WebCommandRejected("invalid_source_action")
        identifier = secrets.token_hex(16) if request_id is None else request_id
        message = {
            "version": 1,
            "token": self._token,
            "request_id": identifier,
            "route": route,
            "payload": payload,
        }
        try:
            encoded = (json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n").encode()
            if len(encoded) > _MAX_MESSAGE_BYTES:
                raise WebCommandRejected("invalid_source_action")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(_TIMEOUT_SECONDS)
                connection.connect(self.socket_path)
                connection.sendall(encoded)
                with connection.makefile("rb") as reader:
                    response_bytes = reader.readline(_MAX_MESSAGE_BYTES + 1)
            if not response_bytes or len(response_bytes) > _MAX_MESSAGE_BYTES:
                raise WebCommandOutcomeUnknown("command response incomplete")
            response = json.loads(response_bytes)
        except (OSError, TimeoutError, UnicodeError, json.JSONDecodeError) as error:
            raise WebCommandOutcomeUnknown("supervisor command outcome unknown") from error
        if not isinstance(response, dict):
            raise WebCommandOutcomeUnknown("invalid supervisor command response")
        if response.get("ok") is not True:
            code = response.get("code")
            if not isinstance(code, str):
                raise WebCommandOutcomeUnknown("invalid supervisor error response")
            raise WebCommandRejected(code)
        result = response.get("result")
        if not isinstance(result, dict):
            raise WebCommandOutcomeUnknown("invalid supervisor success response")
        return cast(dict[str, object], result)


class SupervisorWebCommandBroker:
    """One short-lived, PID-bound command gate for the active UI child."""

    def __init__(self, workspace: Path, socket_path: str) -> None:
        self.workspace = workspace.resolve()
        self.socket_path = socket_path
        self.token = secrets.token_urlsafe(32)
        self._child_pid: int | None = None
        self._lock = threading.Lock()
        self._seen: dict[str, tuple[str, dict[str, object]]] = {}

    def bind_child(self, pid: int) -> None:
        """Bind capability to the actual launched UI process identity."""
        if self._child_pid is not None or isinstance(pid, bool) or pid <= 0:
            raise ValueError("Web command child identity already bound or invalid")
        self._child_pid = pid

    def _peer_authorized(self, connection: socket.socket) -> bool:
        if self._child_pid is None or not hasattr(socket, "SO_PEERCRED"):
            return False
        try:
            credentials = connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            pid, uid, _gid = struct.unpack("3i", credentials)
        except (OSError, ValueError, struct.error):
            return False
        return pid == self._child_pid and uid == os.geteuid()

    def handle(self, connection: socket.socket) -> None:
        connection.settimeout(_TIMEOUT_SECONDS)
        if not self._peer_authorized(connection):
            self._reply(connection, {"ok": False, "code": "write_not_authorized"})
            return
        try:
            with connection.makefile("rb") as reader:
                data = reader.readline(_MAX_MESSAGE_BYTES + 1)
            if not data or len(data) > _MAX_MESSAGE_BYTES:
                self._reply(connection, {"ok": False, "code": "invalid_source_action"})
                return
            request = json.loads(data)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            token = request.get("token")
            if not isinstance(token, str) or not secrets.compare_digest(token, self.token):
                self._reply(connection, {"ok": False, "code": "write_not_authorized"})
                return
            route, payload, identifier = (
                request.get("route"),
                request.get("payload"),
                request.get("request_id"),
            )
            if (
                request.get("version") != 1
                or set(request) != {"version", "token", "request_id", "route", "payload"}
                or not isinstance(route, str)
                or route not in WEB_SOURCE_ACTION_ROUTES
                or not isinstance(payload, dict)
                or any(not isinstance(key, str) for key in payload)
                or not isinstance(identifier, str)
                or len(identifier) != 32
                or any(char not in "0123456789abcdef" for char in identifier)
            ):
                raise ValueError("invalid bounded command")
            identity = json.dumps([route, payload], sort_keys=True, allow_nan=False)
            with self._lock:
                cached = self._seen.get(identifier)
                if cached is not None:
                    response = (
                        cached[1] if cached[0] == identity
                        else {"ok": False, "code": "command_request_conflict"}
                    )
                elif len(self._seen) >= _MAX_REQUESTS_PER_GENERATION:
                    response = {"ok": False, "code": "command_capacity_exceeded"}
                else:
                    response = self._execute(route, cast(dict[str, object], payload))
                    self._seen[identifier] = (identity, response)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            response = {"ok": False, "code": "invalid_source_action"}
        except (OSError, TimeoutError):
            response = {"ok": False, "code": "source_state_unavailable"}
        self._reply(connection, response)

    def _execute(self, route: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return {"ok": True, "result": execute_web_source_action(self.workspace, route, payload)}
        except SourceAlreadyRegisteredError:
            return {"ok": False, "code": "source_id_exists"}
        except SourceControlConflict:
            return {"ok": False, "code": "source_control_conflict"}
        except UnknownRegisteredSourceError:
            return {"ok": False, "code": "source_not_found"}
        except (ValueError, TypeError, UnicodeError, FileNotFoundError, NotADirectoryError):
            return {"ok": False, "code": "invalid_source_action"}
        except (OSError, RuntimeError):
            return {"ok": False, "code": "source_state_unavailable"}

    @staticmethod
    def _reply(connection: socket.socket, response: dict[str, object]) -> None:
        try:
            payload = (json.dumps(response, allow_nan=False, separators=(",", ":")) + "\n").encode()
            if len(payload) > _MAX_MESSAGE_BYTES:
                payload = b'{"ok":false,"code":"source_state_unavailable"}\n'
            connection.sendall(payload)
        except (OSError, TimeoutError):
            # The caller observes outcome_unknown; never reissue its command here.
            pass


class _UnixWebServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


@contextmanager
def open_supervisor_web_command_broker(workspace: Path) -> Iterator[SupervisorWebCommandBroker]:
    """Bind a private ephemeral socket; caller must hold supervisor.lock throughout."""
    if not hasattr(socket, "SO_PEERCRED") or os.name != "posix":
        raise RuntimeError("supervised Web commands require Linux peer credentials")
    with tempfile.TemporaryDirectory(prefix="phm-web-command-") as directory:
        os.chmod(directory, 0o700)
        path = str(Path(directory) / "command.sock")
        broker = SupervisorWebCommandBroker(workspace, path)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                broker.handle(cast(socket.socket, self.request))

        with _UnixWebServer(path, Handler) as server:
            os.chmod(path, 0o600)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield broker
            finally:
                server.shutdown()
                thread.join(timeout=_TIMEOUT_SECONDS)
