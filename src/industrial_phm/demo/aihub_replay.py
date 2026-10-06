"""Packaged AI-Hub 239 power replay engine used by demos and development tools."""

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
from typing import cast
from urllib.parse import urlparse
from uuid import uuid4

from industrial_phm.adapters.aihub_power import archive_sha256, iter_power_observations
from industrial_phm.adapters.aihub_power_history import (
    AIHUB_239_SEMANTICS_V3,
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

MANIFEST = "replay.json"
REPLAY_LOG = "replay-log.jsonl"
_NAMESPACE = "urn:industrial-phm:aihub-239-replay"
ReplayManifest = dict[str, object]


def validate_replay_endpoint(endpoint: str) -> None:
    """Keep packaged replay servers on explicit loopback OPC UA endpoints."""
    parsed = urlparse(endpoint)
    if parsed.scheme != "opc.tcp" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ValueError("AI-Hub replay endpoint must use opc.tcp://127.0.0.1:<port>/...")


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
        if not isinstance(self.archive, Path):
            raise ValueError("archive must be Path")
        if not isinstance(self.member, str) or not self.member.strip():
            raise ValueError("member must not be empty")
        for value in (self.start_local, self.end_local):
            if value.tzinfo is not None:
                raise ValueError("replay selection uses naive source-local time")
        if self.end_local <= self.start_local:
            raise ValueError("replay selection end must follow its start")


def load_replay_records(selection: ReplaySelection) -> tuple[tuple[ReplayRecord, ...], int]:
    """Group selected source observations without inventing values for conflicts."""
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
    if not records:
        raise ValueError("replay records must not be empty")
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or speed <= 0:
        raise ValueError("speed must be positive")
    first = records[0].source_local
    return tuple((record.source_local - first).total_seconds() / float(speed) for record in records)


def replay_channels(records: Sequence[ReplayRecord]) -> tuple[str, ...]:
    return tuple(sorted({channel for record in records for channel in record.values}))


def node_id(channel: str, namespace_index: int = 2) -> str:
    return f"ns={namespace_index};s=AIHub239.{channel}"


def semantic_bindings(
    source_id: str,
    channels: Sequence[str],
    *,
    archive_digest: str,
    member: str,
) -> tuple[ChannelSemanticBinding, ...]:
    """Bind only channels for which the versioned dictionary has evidence."""
    bindings = []
    for channel in channels:
        definition = channel_definition(
            AIHUB_239_SEMANTICS_V3,
            channel,
            archive_sha256=archive_digest,
            member=member,
        )
        if definition.unit is None:
            continue
        bindings.append(
            ChannelSemanticBinding(
                source_id=source_id,
                channel_id=channel,
                version=AIHUB_239_SEMANTICS_V3,
                definition=definition,
                interpretation_evidence=(
                    "AI-Hub 239 ITEM_NAME replayed unchanged over local OPC UA; provider unit "
                    "table and observed data agree"
                ),
            )
        )
    return tuple(bindings)


def build_replay_manifest(
    endpoint: str,
    selection: ReplaySelection,
    *,
    prepared_at: datetime | None = None,
) -> ReplayManifest:
    """Build replay provenance and validate the selected archive range."""
    validate_replay_endpoint(endpoint)
    records, conflicts = load_replay_records(selection)
    channels = replay_channels(records)
    digest = archive_sha256(selection.archive)
    now = datetime.now(UTC) if prepared_at is None else prepared_at
    if now.utcoffset() is None:
        raise ValueError("prepared_at must be timezone-aware")
    bindings = semantic_bindings(
        selection.binding.source_id,
        channels,
        archive_digest=digest,
        member=selection.member,
    )
    return {
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
        "bound_channels": [binding.channel_id for binding in bindings],
        "conflicting_values_published_bad": conflicts,
        "prepared_at": now.isoformat(),
    }


def build_registered_replay_source(
    selection: ReplaySelection,
    manifest: ReplayManifest,
    *,
    name: str,
    registered_at: datetime,
    asset_display_name: str | None = None,
) -> RegisteredSource:
    """Project a validated manifest into the normal registered-source contract."""
    if registered_at.utcoffset() is None:
        raise ValueError("registered_at must be timezone-aware")
    channels = _manifest_string_list(manifest, "channels")
    digest = _manifest_string(manifest, "archive_sha256")
    endpoint = _manifest_string(manifest, "endpoint")
    source_id = selection.binding.source_id
    bindings = semantic_bindings(
        source_id,
        channels,
        archive_digest=digest,
        member=selection.member,
    )
    return RegisteredSource(
        source_id=source_id,
        name=name,
        config=OpcUaSourceConfig(
            endpoint_url=endpoint,
            asset_id=selection.binding.asset_id,
            node_mappings=tuple(
                OpcUaNodeMapping(channel, node_id(channel)) for channel in channels
            ),
            timeout_seconds=2.0,
            semantic_bindings=bindings,
            asset_display_name=asset_display_name,
        ),
        registered_at=registered_at,
    )


def register_replay_source(
    root: Path,
    selection: ReplaySelection,
    manifest: ReplayManifest,
    *,
    name: str,
    desired_state: CollectionDesiredState,
    registered_at: datetime,
    asset_display_name: str | None = None,
) -> RegisteredSource:
    """Register one replay source into an already chosen local state root."""
    source = build_registered_replay_source(
        selection,
        manifest,
        name=name,
        registered_at=registered_at,
        asset_display_name=asset_display_name,
    )
    sources = JsonSourceRepository(root / "sources.json")
    sources.register(source)
    transition_source_lifecycle(
        sources,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=registered_at,
    )
    request_collection_state(
        sources,
        sources,
        SqliteCollectionControlRepository(root / "control.sqlite"),
        source.source_id,
        desired_state,
        requested_at=registered_at,
    )
    return source


def write_replay_manifest(root: Path, manifest: ReplayManifest) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare(
    root: Path,
    endpoint: str,
    selection: ReplaySelection,
    *,
    name: str,
    asset_display_name: str | None = None,
) -> ReplayManifest:
    """Development helper: prepare an empty root and leave collection STOPPED."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("replay root must be empty; reuse prepared state instead")
    manifest = build_replay_manifest(endpoint, selection)
    prepared_at = datetime.fromisoformat(_manifest_string(manifest, "prepared_at"))
    register_replay_source(
        root,
        selection,
        manifest,
        name=name,
        desired_state=CollectionDesiredState.STOPPED,
        registered_at=prepared_at,
        asset_display_name=asset_display_name,
    )
    write_replay_manifest(root, manifest)
    return manifest


def load_selection(root: Path) -> tuple[ReplayManifest, ReplaySelection]:
    raw = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("replay manifest root must be an object")
    manifest = cast(ReplayManifest, raw)
    binding_raw = manifest.get("binding")
    if not isinstance(binding_raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in binding_raw.items()
    ):
        raise ValueError("replay manifest binding must contain string fields")
    binding = PowerHistoryBinding(**cast(dict[str, str], binding_raw))
    selection = ReplaySelection(
        archive=Path(_manifest_string(manifest, "archive")),
        member=_manifest_string(manifest, "member"),
        binding=binding,
        start_local=datetime.fromisoformat(_manifest_string(manifest, "start_local")),
        end_local=datetime.fromisoformat(_manifest_string(manifest, "end_local")),
    )
    if archive_sha256(selection.archive) != _manifest_string(manifest, "archive_sha256"):
        raise ValueError("archive changed since the replay was prepared")
    return manifest, selection


def _log(root: Path, entry: dict[str, object]) -> None:
    with (root / REPLAY_LOG).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def serve(
    root: Path,
    stop: asyncio.Event,
    *,
    speed: float,
    loop: bool,
    omit_channels: Sequence[str] = (),
    freeze_after_records: int | None = None,
    publish_ledger: Path | None = None,
) -> None:
    """Publish recorded values on a rebased clock without changing their values."""
    run_id = uuid4().hex
    manifest, selection = load_selection(root)
    records, _ = load_replay_records(selection)
    offsets = replay_offsets(records, speed)
    channels = tuple(_manifest_string_list(manifest, "channels"))
    unknown = set(omit_channels) - set(channels)
    if unknown:
        raise ValueError(f"unknown channels to omit: {sorted(unknown)}")
    period = offsets[1] if len(offsets) > 1 else 1.0 / speed
    asyncua = importlib.import_module("asyncua")
    ua = asyncua.ua
    server = asyncua.Server()
    await server.init()
    server.set_endpoint(_manifest_string(manifest, "endpoint"))
    server.set_server_name("industrial-phm AI-Hub 239 replay")
    namespace = await server.register_namespace(_NAMESPACE)
    if namespace != 2:
        raise RuntimeError("replay namespace index must be 2 to match the prepared mapping")
    device = await server.nodes.objects.add_object(namespace, "AIHub239Replay")
    nodes = {
        channel: await device.add_variable(
            ua.NodeId(f"AIHub239.{channel}", namespace),
            channel,
            0.0,
        )
        for channel in channels
    }
    waiting_status = ua.StatusCode(ua.StatusCodes.BadWaitingForInitialData)
    for node in nodes.values():
        await node.write_value(
            ua.DataValue(ua.Variant(None, ua.VariantType.Null), StatusCode=waiting_status)
        )

    published = 0
    cycle = 0
    async with server:
        print(f"AI-Hub replay OPC UA server: {_manifest_string(manifest, 'endpoint')}", flush=True)
        while not stop.is_set():
            started = datetime.now(UTC)
            _log(
                root,
                {
                    "cycle": cycle,
                    "replay_started_at": started.isoformat(),
                    "source_start_local": records[0].source_local.isoformat(),
                    "speed": speed,
                    "rule": (
                        "replay_at = replay_started_at + "
                        "(source_local - source_start_local) / speed"
                    ),
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
                written: dict[str, float | None] = {}
                for channel, value in record.values.items():
                    if channel in omit_channels:
                        continue
                    written[channel] = value
                    status = ua.StatusCode(
                        ua.StatusCodes.Good if value is not None else ua.StatusCodes.Bad
                    )
                    variant = (
                        ua.Variant(None, ua.VariantType.Null)
                        if value is None
                        else ua.Variant(value, ua.VariantType.Double)
                    )
                    await nodes[channel].write_value(
                        ua.DataValue(
                            variant,
                            StatusCode=status,
                            SourceTimestamp=at,
                            ServerTimestamp=datetime.now(UTC),
                        )
                    )
                if publish_ledger is not None:
                    with publish_ledger.open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                {
                                    "run": run_id,
                                    "at": at.isoformat(),
                                    "values": written,
                                    "good": {
                                        channel: value is not None
                                        for channel, value in written.items()
                                    },
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
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


def main(argv: Sequence[str] | None = None) -> int:
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
    prepare_parser.add_argument(
        "--asset-display-name",
        help="optional presentation label for the asset; the binding asset_id stays its identity",
    )

    server_parser = commands.add_parser("server", help="publish the prepared selection")
    server_parser.add_argument("--root", type=Path, required=True)
    server_parser.add_argument(
        "--speed",
        type=float,
        default=60.0,
        help="recorded seconds per replay second",
    )
    server_parser.add_argument("--loop", action="store_true", help="repeat the selection")
    server_parser.add_argument(
        "--omit-channel",
        action="append",
        default=[],
        help="never publish this channel",
    )
    server_parser.add_argument(
        "--publish-ledger",
        type=Path,
        help="append every written record as JSON lines (audit ground truth)",
    )
    server_parser.add_argument(
        "--freeze-after-records",
        type=int,
        help="keep serving but stop updating values after this many records",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            binding_raw = json.loads(args.binding.read_text(encoding="utf-8"))
            if not isinstance(binding_raw, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in binding_raw.items()
            ):
                raise ValueError("binding file must contain string fields")
            selection = ReplaySelection(
                archive=args.archive,
                member=args.member,
                binding=PowerHistoryBinding(**cast(dict[str, str], binding_raw)),
                start_local=args.start,
                end_local=args.end,
            )
            manifest = prepare(
                args.root,
                args.endpoint,
                selection,
                name=args.name,
                asset_display_name=args.asset_display_name,
            )
            print(
                f"Prepared {args.root}: {_manifest_int(manifest, 'record_count')} records, "
                f"{len(_manifest_string_list(manifest, 'channels'))} channels "
                f"({len(_manifest_string_list(manifest, 'bound_channels'))} "
                "with evidenced meaning); "
                "collection STOPPED"
            )
            return 0

        async def run() -> None:
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for item in (signal.SIGINT, signal.SIGTERM):
                with suppress(NotImplementedError):
                    loop.add_signal_handler(item, stop.set)
            await serve(
                args.root,
                stop,
                speed=args.speed,
                loop=args.loop,
                omit_channels=args.omit_channel,
                freeze_after_records=args.freeze_after_records,
                publish_ledger=args.publish_ledger,
            )

        asyncio.run(run())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        return 1
    return 0


def _manifest_string(manifest: ReplayManifest, key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"replay manifest {key} must be a non-empty string")
    return value


def _manifest_string_list(manifest: ReplayManifest, key: str) -> list[str]:
    value = manifest.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"replay manifest {key} must be a string list")
    return cast(list[str], value)


def _manifest_int(manifest: ReplayManifest, key: str) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"replay manifest {key} must be an integer")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
