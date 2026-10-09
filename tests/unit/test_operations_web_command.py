"""Supervisor Web command IPC authorization, replay and failure contracts."""

from __future__ import annotations

import os
import socket
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

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


def test_parallel_same_request_id_replays_once_and_detects_payload_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contending callers share one result; conflicting reuse cannot mutate twice."""
    entered = Event()
    release = Event()
    calls: list[dict[str, object]] = []

    def execute(_root: Path, _route: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        entered.set()
        assert release.wait(timeout=4), "test failed to release pending command"
        return {"executions": len(calls)}

    monkeypatch.setattr(command, "execute_web_source_action", execute)
    route = "/api/v1/sources/lifecycle"
    request_id = "c" * 32
    payload: dict[str, object] = {"source_id": "a"}
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)

        def replay(body: dict[str, object]) -> tuple[str, object]:
            try:
                return ("ok", client.execute(route, body, request_id=request_id))
            except command.WebCommandRejected as error:
                return ("rejected", error.code)

        with ThreadPoolExecutor(max_workers=12) as executor:
            first = executor.submit(client.execute, route, payload, request_id=request_id)
            try:
                assert entered.wait(timeout=3), "first IPC dispatch did not begin"
                same = [executor.submit(replay, payload) for _ in range(7)]
                changed = [executor.submit(replay, {"source_id": "b"}) for _ in range(4)]
            finally:
                release.set()
            assert first.result(timeout=6) == {"executions": 1}
            assert [future.result(timeout=6) for future in same] == [
                ("ok", {"executions": 1})
            ] * 7
            assert [future.result(timeout=6) for future in changed] == [
                ("rejected", "command_request_conflict")
            ] * 4
    assert calls == [payload]


def test_lost_ipc_reply_does_not_automatically_repeat_completed_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed reply cannot be interpreted as a failed write."""
    calls: list[dict[str, object]] = []

    def execute(_root: Path, _route: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        return {"executions": len(calls)}

    monkeypatch.setattr(command, "execute_web_source_action", execute)
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)
        original_reply = broker._reply
        drop_first = True

        def lose_one_reply(connection: socket.socket, response: dict[str, object]) -> None:
            nonlocal drop_first
            if drop_first:
                drop_first = False
                return
            original_reply(connection, response)

        monkeypatch.setattr(broker, "_reply", lose_one_reply)
        route = "/api/v1/sources/lifecycle"
        body: dict[str, object] = {"source_id": "a"}
        request_id = "d" * 32
        with pytest.raises(command.WebCommandOutcomeUnknown):
            client.execute(route, body, request_id=request_id)
        assert calls == [body]
        # Only an explicit, same-generation, same-ID replay can read the cached result.
        assert client.execute(route, body, request_id=request_id) == {"executions": 1}
        assert calls == [body]


def test_command_replay_cache_reaches_bounded_capacity_without_eviction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not silently evict completed IDs and accidentally re-execute them."""
    monkeypatch.setattr(command, "_MAX_REQUESTS_PER_GENERATION", 2)
    calls: list[dict[str, object]] = []

    def execute(_root: Path, _route: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        return {"executions": len(calls)}

    monkeypatch.setattr(command, "execute_web_source_action", execute)
    with command.open_supervisor_web_command_broker(tmp_path) as broker:
        broker.bind_child(os.getpid())
        client = command.WebCommandClient(broker.socket_path, broker.token)
        route = "/api/v1/sources/lifecycle"
        first: dict[str, object] = {"source_id": "a"}
        second: dict[str, object] = {"source_id": "b"}
        assert client.execute(route, first, request_id="a" * 32) == {"executions": 1}
        assert client.execute(route, second, request_id="b" * 32) == {"executions": 2}
        with pytest.raises(command.WebCommandRejected, match="command_capacity_exceeded"):
            client.execute(route, {"source_id": "c"}, request_id="c" * 32)
        assert client.execute(route, first, request_id="a" * 32) == {"executions": 1}
        with pytest.raises(command.WebCommandRejected, match="command_request_conflict"):
            client.execute(route, second, request_id="a" * 32)
    assert calls == [first, second]
