"""Replay one explicit AI-Hub 239 power selection as a local OPC UA source.

The replay stands in for a site OPC UA server during local validation. It publishes
recorded values unchanged; only time is rebased onto the replay clock, because a
live collector judges lateness and freshness against wall time. The mapping from
replay time back to the recorded source time is written to ``replay-log.jsonl``.

OPC UA DataChange reports only changed values, as a real subscription does, so an
unchanged recorded value produces no notification.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import signal
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.adapters.aihub_power import archive_sha256, iter_power_observations
from industrial_phm.adapters.aihub_power_history import (
    AIHUB_239_SEMANTICS_V2,
    PowerHistoryBinding,
    channel_definition,
)
from industrial_phm.application import (
    ChannelSemanticBinding,
    CollectionDesiredState,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    request_collection_state,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import SqliteCollectionControlRepository
from tools.opcua.demo import validate_endpoint

MANIFEST = "replay.json"
REPLAY_LOG = "replay-log.jsonl"
_NAMESPACE = "urn:industrial-phm:aihub-239-replay"


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    """All channel values recorded at one source-local timestamp."""

    source_local: datetime
    values: dict[str, float | None]


@dataclass(frozen=True, slots=True)
class ReplaySelection:
    archive: Path
    member: str
    binding: PowerHistoryBinding
    start_local: datetime
    end_local: datetime

    def __post_init__(self) -> None:
        for value in (self.start_local, self.end_local):
            if value.tzinfo is not None:
                raise ValueError("replay selection uses naive source-local time")
        if self.end_local <= self.start_local:
            raise ValueError("replay selection end must follow its start")


def load_replay_records(selection: ReplaySelection) -> tuple[tuple[ReplayRecord, ...], int]:
    """Group the selected observations by source timestamp.

    Returns the records and the number of channel values published as bad because
    one timestamp recorded different values for the same channel.
    """
    grouped: dict[datetime, dict[str, float | None]] = {}
    conflicts: set[tuple[datetime, str]] = set()
    for observation in iter_power_observations(selection.archive, selection.member):
        if (observation.device_id, observation.device_board_id) != (
            selection.binding.device_id,
            selection.binding.device_board_id,
        ):
            raise ValueError("member source identifiers do not match the explicit binding")
        local = datetime.fromisoformat(observation.timestamp_text)
        if not selection.start_local <= local < selection.end_local:
            continue
        values = grouped.setdefault(local, {})
        channel = observation.channel_name
        if channel in values and values[channel] != observation.value:
            conflicts.add((local, channel))
        values[channel] = observation.value
    for local, channel in conflicts:
        grouped[local][channel] = None
    if not grouped:
        raise ValueError("replay selection contains no observations")
    records = tuple(ReplayRecord(local, grouped[local]) for local in sorted(grouped))
    return records, len(conflicts)


def replay_offsets(records: Sequence[ReplayRecord], speed: float) -> tuple[float, ...]:
    """Seconds after replay start for each record; recorded spacing divided by speed."""
    if not speed > 0:
        raise ValueError("speed must be positive")
    first = records[0].source_local
    return tuple((r.source_local - first).total_seconds() / speed for r in records)


def replay_channels(records: Sequence[ReplayRecord]) -> tuple[str, ...]:
    return tuple(sorted({channel for record in records for channel in record.values}))


def node_id(channel: str, namespace_index: int = 2) -> str:
    return f"ns={namespace_index};s=AIHub239.{channel}"


def semantic_bindings(
    source_id: str, channels: Sequence[str], *, archive_digest: str, member: str
) -> tuple[ChannelSemanticBinding, ...]:
    """Bind only channels the AI-Hub dictionary resolves; others stay unresolved."""
    bindings = []
    for channel in channels:
        definition = channel_definition(
            AIHUB_239_SEMANTICS_V2, channel, archive_sha256=archive_digest, member=member
        )
        if definition.unit is None:
            continue
        bindings.append(
            ChannelSemanticBinding(
                source_id=source_id,
                channel_id=channel,
                version=AIHUB_239_SEMANTICS_V2,
                definition=definition,
                interpretation_evidence=(
                    "AI-Hub 239 ITEM_NAME replayed unchanged over local OPC UA; provider unit "
                    "table and observed data agree"
                ),
            )
        )
    return tuple(bindings)


def prepare(root: Path, endpoint: str, selection: ReplaySelection, *, name: str) -> dict:
    """Register the replay as an ACTIVE OPC UA source with collection STOPPED."""
    validate_endpoint(endpoint)
    if root.exists() and any(root.iterdir()):
        raise ValueError("replay root must be empty; reuse prepared state instead")
    records, conflicts = load_replay_records(selection)
    channels = replay_channels(records)
    digest = archive_sha256(selection.archive)
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    source_id = selection.binding.source_id
    bindings = semantic_bindings(
        source_id, channels, archive_digest=digest, member=selection.member
    )
    sources = JsonSourceRepository(root / "sources.json")
    sources.register(
        RegisteredSource(
            source_id=source_id,
            name=name,
            config=OpcUaSourceConfig(
                endpoint_url=endpoint,
                asset_id=selection.binding.asset_id,
                node_mappings=tuple(OpcUaNodeMapping(c, node_id(c)) for c in channels),
                timeout_seconds=2.0,
                semantic_bindings=bindings,
            ),
            registered_at=now,
        )
    )
    transition_source_lifecycle(sources, source_id, SourceLifecycleState.ACTIVE, changed_at=now)
    request_collection_state(
        sources,
        sources,
        SqliteCollectionControlRepository(root / "control.sqlite"),
        source_id,
        CollectionDesiredState.STOPPED,
        requested_at=now,
    )
    manifest = {
        "schema": "aihub-239-opcua-replay-v1",
        "endpoint": endpoint,
        "archive": str(selection.archive),
        "archive_sha256": digest,
        "member": selection.member,
        "binding": asdict(selection.binding),
        "start_local": selection.start_local.isoformat(),
        "end_local": selection.end_local.isoformat(),
        "record_count": len(records),
        "channels": list(channels),
        "bound_channels": [b.channel_id for b in bindings],
        "conflicting_values_published_bad": conflicts,
        "prepared_at": now.isoformat(),
    }
    (root / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def load_selection(root: Path) -> tuple[dict, ReplaySelection]:
    manifest = json.loads((root / MANIFEST).read_text())
    selection = ReplaySelection(
        archive=Path(manifest["archive"]),
        member=manifest["member"],
        binding=PowerHistoryBinding(**manifest["binding"]),
        start_local=datetime.fromisoformat(manifest["start_local"]),
        end_local=datetime.fromisoformat(manifest["end_local"]),
    )
    if archive_sha256(selection.archive) != manifest["archive_sha256"]:
        raise ValueError("archive changed since the replay was prepared")
    return manifest, selection


def _log(root: Path, entry: dict) -> None:
    with (root / REPLAY_LOG).open("a") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def serve(
    root: Path,
    stop: asyncio.Event,
    *,
    speed: float,
    loop: bool,
    omit_channels: Sequence[str] = (),
    freeze_after_records: int | None = None,
) -> None:
    """Publish records on the replay clock until the selection ends or ``stop``.

    ``omit_channels`` never publishes those channels (a missing phase);
    ``freeze_after_records`` keeps the server up but stops updating (stale data).
    """
    manifest, selection = load_selection(root)
    records, _ = load_replay_records(selection)
    offsets = replay_offsets(records, speed)
    channels = tuple(manifest["channels"])
    unknown = set(omit_channels) - set(channels)
    if unknown:
        raise ValueError(f"unknown channels to omit: {sorted(unknown)}")
    # One nominal record gap separates loop cycles on the replay clock.
    period = offsets[1] if len(offsets) > 1 else 1.0 / speed
    asyncua = importlib.import_module("asyncua")
    ua = asyncua.ua
    server = asyncua.Server()
    await server.init()
    server.set_endpoint(manifest["endpoint"])
    server.set_server_name("industrial-phm AI-Hub 239 replay")
    namespace = await server.register_namespace(_NAMESPACE)
    if namespace != 2:
        raise RuntimeError("replay namespace index must be 2 to match the prepared mapping")
    device = await server.nodes.objects.add_object(namespace, "AIHub239Replay")
    nodes = {
        channel: await device.add_variable(
            ua.NodeId(f"AIHub239.{channel}", namespace), channel, 0.0
        )
        for channel in channels
    }
    published = 0
    cycle = 0
    async with server:
        print(f"AI-Hub replay OPC UA server: {manifest['endpoint']}", flush=True)
        while not stop.is_set():
            started = datetime.now(UTC)
            _log(
                root,
                {
                    "cycle": cycle,
                    "replay_started_at": started.isoformat(),
                    "source_start_local": records[0].source_local.isoformat(),
                    "speed": speed,
                    "rule": "replay_at = replay_started_at + (source_local - source_start_local)"
                    " / speed",
                },
            )
            for record, offset in zip(records, offsets, strict=True):
                at = started + timedelta(seconds=offset)
                with suppress(TimeoutError):
                    delay = (at - datetime.now(UTC)).total_seconds()
                    await asyncio.wait_for(stop.wait(), timeout=max(0.0, delay))
                if stop.is_set():
                    return
                if freeze_after_records is not None and published >= freeze_after_records:
                    continue
                for channel, value in record.values.items():
                    if channel in omit_channels:
                        continue
                    status = ua.StatusCode(
                        ua.StatusCodes.Good if value is not None else ua.StatusCodes.Bad
                    )
                    await nodes[channel].write_value(
                        ua.DataValue(
                            ua.Variant(0.0 if value is None else value, ua.VariantType.Double),
                            StatusCode=status,
                            SourceTimestamp=at,
                            ServerTimestamp=datetime.now(UTC),
                        )
                    )
                published += 1
                if published % 60 == 0:
                    print(
                        f"cycle {cycle} record {published}: source {record.source_local} "
                        f"published as {at.isoformat()}",
                        flush=True,
                    )
            if not loop:
                print("replay selection finished; server stays up without new values", flush=True)
                await stop.wait()
                return
            cycle += 1
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=period)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="register the replay source")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--endpoint", required=True)
    prepare_parser.add_argument("--archive", type=Path, required=True)
    prepare_parser.add_argument("--member", required=True)
    prepare_parser.add_argument("--binding", type=Path, required=True)
    prepare_parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    prepare_parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    prepare_parser.add_argument("--name", default="AI-Hub 239 recorded power (OPC UA replay)")
    server_parser = commands.add_parser("server", help="publish the prepared selection")
    server_parser.add_argument("--root", type=Path, required=True)
    server_parser.add_argument(
        "--speed", type=float, default=60.0, help="recorded seconds per replay second"
    )
    server_parser.add_argument("--loop", action="store_true", help="repeat the selection")
    server_parser.add_argument(
        "--omit-channel", action="append", default=[], help="never publish this channel"
    )
    server_parser.add_argument(
        "--freeze-after-records",
        type=int,
        help="keep serving but stop updating values after this many records",
    )
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            selection = ReplaySelection(
                archive=args.archive,
                member=args.member,
                binding=PowerHistoryBinding(**json.loads(args.binding.read_text())),
                start_local=args.start,
                end_local=args.end,
            )
            manifest = prepare(args.root, args.endpoint, selection, name=args.name)
            print(
                f"Prepared {args.root}: {manifest['record_count']} records, "
                f"{len(manifest['channels'])} channels ({len(manifest['bound_channels'])} with "
                "evidenced meaning); collection STOPPED"
            )
            return

        async def run() -> None:
            stop = asyncio.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                asyncio.get_running_loop().add_signal_handler(sig, stop.set)
            await serve(
                args.root,
                stop,
                speed=args.speed,
                loop=args.loop,
                omit_channels=args.omit_channel,
                freeze_after_records=args.freeze_after_records,
            )

        asyncio.run(run())
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
