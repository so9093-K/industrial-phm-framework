"""A local anonymous OPC UA server with one variable, for Web connection tests."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread

import pytest


@contextmanager
def local_opcua_server() -> Iterator[tuple[str, str]]:
    asyncua = pytest.importorskip("asyncua")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    endpoint = f"opc.tcp://127.0.0.1:{port}/industrial-phm/"
    ready, stopped = Event(), Event()
    captured: dict[str, object] = {}

    async def serve() -> None:
        server = asyncua.Server()
        await server.init()
        server.set_endpoint(endpoint)
        namespace = await server.register_namespace("urn:industrial-phm:web-opcua")
        machine = await server.nodes.objects.add_object(namespace, "Machine")
        vibration = await machine.add_variable(namespace, "VibrationX", 12.5)
        captured["node_id"] = vibration.nodeid.to_string()
        async with server:
            ready.set()
            while not stopped.is_set():
                await asyncio.sleep(0.05)

    def runner() -> None:
        try:
            asyncio.run(serve())
        except Exception as error:
            captured["error"] = error
            ready.set()

    thread = Thread(target=runner, daemon=True)
    thread.start()
    try:
        assert ready.wait(30), "local OPC UA fixture did not start"
        assert "error" not in captured, str(captured.get("error"))
        yield endpoint, str(captured["node_id"])
    finally:
        stopped.set()
        thread.join(timeout=30)
        assert not thread.is_alive()
