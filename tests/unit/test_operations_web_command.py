"""Supervisor Web command IPC authorization, replay and failure contracts."""

from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from industrial_phm.runtime import operations_web_command as command


def test_broker_is_private_pid_bound_and_dispatches_exact_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str, dict[str, object]]] = []

    def execute(root: Path, route: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((root, route, payload))
        return {"source_id": "source-a", "registration_state": "registered"}

    monkeypatch.setattr(command, "execute_web_source_action", execute)
    route = "/api/v1/sources/file"
    body: dict[str, object] = {"source_id": "source-a"}
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        assert stat.S_IMODE(os.stat(broker.socket_path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(Path(broker.socket_path).parent).st_mode) == 0o700
        unbound = command.WebCommandClient(broker.socket_path, broker.token)
        with pytest.raises(command.WebCommandRejected, match="write_not_authorized"):
            unbound.execute(route, body)
        broker.bind_child(os.getpid())
        with pytest.raises(ValueError, match="already bound"):
            broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)
        result = client.execute(route, body)
        assert result["registration_state"] == "registered"
        assert calls == [(tmp_path.resolve(), route, body)]
        bad_token = command.WebCommandClient(broker.socket_path, "wrong")
        with pytest.raises(command.WebCommandRejected, match="write_not_authorized"):
            bad_token.execute(route, body)
        with pytest.raises(command.WebCommandRejected, match="invalid_source_action"):
            client.execute("/api/v1/reviews/arbitrary", body)
    with pytest.raises(command.WebCommandOutcomeUnknown):
        client.execute(route, body)
    assert calls == [(tmp_path.resolve(), route, body)]


def test_broker_rejects_other_pid_even_with_correct_token(tmp_path: Path) -> None:
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid() + 1)
        client = command.WebCommandClient(broker.socket_path, broker.token)
        with pytest.raises(command.WebCommandRejected, match="write_not_authorized"):
            client.execute("/api/v1/sources/file", {"source_id": "source-a"})


def test_command_request_id_replay_is_at_most_once_within_one_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def execute(_root: Path, _route: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        return {"count": len(calls)}

    monkeypatch.setattr(command, "execute_web_source_action", execute)
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)
        route = "/api/v1/sources/collection"
        key = "a" * 32
        assert client.execute(route, {"source_id": "a"}, request_id=key) == {"count": 1}
        assert client.execute(route, {"source_id": "a"}, request_id=key) == {"count": 1}
        with pytest.raises(command.WebCommandRejected, match="command_request_conflict"):
            client.execute(route, {"source_id": "b"}, request_id=key)
        assert calls == [{"source_id": "a"}]


def test_broker_serializes_concurrent_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def execute(_root: Path, _route: str, payload: dict[str, object]) -> dict[str, object]:
        number = payload["sequence"]
        assert isinstance(number, int)
        calls.append(number)
        return {"sequence": number}

    monkeypatch.setattr(command, "execute_web_source_action", execute)
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)

        def submit(n: int) -> dict[str, object]:
            return client.execute("/api/v1/sources/lifecycle", {"sequence": n})

        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(submit, range(24)))
    assert {result["sequence"] for result in results} == set(range(24))
    assert sorted(calls) == list(range(24))


def test_invalid_route_and_oversized_request_never_reach_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        command,
        "execute_web_source_action",
        lambda *args: calls.append(args),
    )
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)
        with pytest.raises(command.WebCommandRejected, match="invalid_source_action"):
            client.execute("/api/v1/source/unknown", {})
        with pytest.raises(command.WebCommandRejected, match="invalid_source_action"):
            client.execute("/api/v1/sources/file", {"data": "x" * 10_000})
        with pytest.raises(command.WebCommandRejected, match="invalid_source_action"):
            client.execute("/api/v1/sources/file", {}, request_id="not-a-hex-id")
        assert calls == []


def test_failing_facade_returns_bounded_code_without_exception_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_root: Path, _route: str, _payload: dict[str, object]) -> dict[str, object]:
        raise OSError("private /secrets/workspace/path")

    monkeypatch.setattr(command, "execute_web_source_action", fail)
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)
        with pytest.raises(command.WebCommandRejected) as error:
            client.execute("/api/v1/sources/collection", {})
        assert error.value.code == "source_state_unavailable"
        assert "/secrets/" not in str(error.value)
