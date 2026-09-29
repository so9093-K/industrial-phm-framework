"""Local synthetic power collection demo, isolated from research/raw data."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import math
import signal
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from industrial_phm.application import (
    CollectionDesiredState,
    FileSourceConfig,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    backfill_registered_file_source,
    request_collection_state,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import SqliteCollectionControlRepository

ASSET = "demo-power-01"
SOURCE = "demo-opcua"
CHANNELS = ("active_power", "voltage")


def validate_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "opc.tcp" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ValueError("demo endpoint must use opc.tcp://127.0.0.1:<port>/...")


def prepare(root: Path, endpoint: str) -> None:
    """Create a fresh, explicitly synthetic FILE/live mapping and seed history."""
    validate_endpoint(endpoint)
    if root.exists() and any(root.iterdir()):
        raise ValueError(
            "demo root must be empty; reuse prepared state without running prepare again"
        )
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    now = datetime.now(UTC)
    csv = root / "historical.csv"
    csv.write_text(
        "timestamp,active_power,voltage\n"
        + "".join(
            f"{(now - timedelta(minutes=30 - i)).isoformat()},{100 + i},{220 + i % 3}\n"
            for i in range(30)
        )
    )
    sources = JsonSourceRepository(root / "sources.json")
    sources.register(
        RegisteredSource(
            source_id="demo-file",
            name="Synthetic historical power observations",
            config=FileSourceConfig(
                source_path=str(csv),
                asset_id=ASSET,
                channel_columns=CHANNELS,
                timestamp_column="timestamp",
            ),
            registered_at=now,
        )
    )
    sources.register(
        RegisteredSource(
            source_id=SOURCE,
            name="Synthetic live power observations",
            config=OpcUaSourceConfig(
                endpoint_url=endpoint,
                asset_id=ASSET,
                node_mappings=tuple(OpcUaNodeMapping(name, f"ns=2;s={name}") for name in CHANNELS),
                timeout_seconds=2.0,
            ),
            registered_at=now,
        )
    )
    transition_source_lifecycle(sources, SOURCE, SourceLifecycleState.ACTIVE, changed_at=now)
    control = SqliteCollectionControlRepository(root / "control.sqlite")
    request_collection_state(
        sources, sources, control, SOURCE, CollectionDesiredState.STOPPED, requested_at=now
    )
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(root / "catalog.sqlite", root / "data")
    )
    result = backfill_registered_file_source(sources, history, "demo-file")
    print(f"Prepared {root}: {result.event_count} synthetic FILE observations; collection STOPPED")


async def run_simulator(endpoint: str, stop: asyncio.Event, *, interval: float = 1.0) -> None:
    validate_endpoint(endpoint)
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("interval must be positive and finite")
    asyncua = importlib.import_module("asyncua")
    ua = asyncua.ua
    server = asyncua.Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name("industrial-phm synthetic power demo")
    namespace = await server.register_namespace("urn:industrial-phm:synthetic-power")
    machine = await server.nodes.objects.add_object(namespace, "SyntheticPower")
    nodes = [await machine.add_variable(ua.NodeId(name, namespace), name, 0.0) for name in CHANNELS]
    index = 0
    async with server:
        print(f"Synthetic OPC UA server: {endpoint}", flush=True)
        while not stop.is_set():
            now = datetime.now(UTC)
            values = (100 + 20 * math.sin(index / 5), 220 + 2 * math.cos(index / 7))
            for node, value in zip(nodes, values, strict=True):
                await node.write_value(
                    ua.DataValue(
                        ua.Variant(value, ua.VariantType.Double),
                        SourceTimestamp=now,
                        ServerTimestamp=now,
                    )
                )
            index += 1
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "server"))
    parser.add_argument("--root", type=Path, default=Path("artifacts/live-demo"))
    parser.add_argument("--endpoint", default="opc.tcp://127.0.0.1:4841/phm-demo/")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root, args.endpoint)
    else:

        async def run() -> None:
            stop = asyncio.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                asyncio.get_running_loop().add_signal_handler(sig, stop.set)
            await run_simulator(args.endpoint, stop)

        asyncio.run(run())


if __name__ == "__main__":
    main()
