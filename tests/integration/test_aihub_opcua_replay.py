import asyncio
import dataclasses
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest

from industrial_phm.adapters.aihub_power_history import AIHUB_239_SEMANTICS_V3, PowerHistoryBinding
from industrial_phm.application import JsonSourceRepository
from industrial_phm.runtime import SqliteCollectionControlRepository

pytest.importorskip("ijson")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support.aihub import treat_archive_as_profiled
from tools.opcua import aihub_replay

MEMBER = "보일러/SourceData_1.json"
LOCAL = datetime(2020, 11, 14, 8, 0)
BINDING = PowerHistoryBinding(
    source_id="replay-boiler",
    asset_id="boiler-asset",
    device_id="5764",
    device_board_id="1",
    timezone="Asia/Seoul",
    identity_evidence="test grouping",
    timezone_evidence="test assumption",
    version="test-v1",
)


def _archive(tmp_path: Path, *, conflict: bool = False) -> Path:
    data = []
    for minute in range(4):
        stamp = (LOCAL + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S")
        for phase, volt in (("R", 220), ("S", 230), ("T", 225 + minute)):
            data.append({"ITEM_NAME": f"{phase}상전압", "ITEM_VALUE": volt, "TIMESTAMP": stamp})
        data.append({"ITEM_NAME": "유효전력평균", "ITEM_VALUE": 5 + minute, "TIMESTAMP": stamp})
    if conflict:
        stamp = (LOCAL + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        data.append({"ITEM_NAME": "R상전압", "ITEM_VALUE": 999, "TIMESTAMP": stamp})
    path = tmp_path / "boiler.zip"
    with ZipFile(path, "w") as archive:
        payload = {"DEVICE_ID": 5764, "DEVICE_BD_ID": 1, "data": data}
        archive.writestr(MEMBER, json.dumps(payload, ensure_ascii=False))
    return path


def _selection(archive: Path, **changes) -> aihub_replay.ReplaySelection:
    fields = {
        "archive": archive,
        "member": MEMBER,
        "binding": BINDING,
        "start_local": LOCAL + timedelta(minutes=1),
        "end_local": LOCAL + timedelta(minutes=4),
    }
    return aihub_replay.ReplaySelection(**(fields | changes))


def test_records_group_one_timestamp_and_publish_conflicts_as_bad(tmp_path):
    records, conflicts = aihub_replay.load_replay_records(
        _selection(_archive(tmp_path, conflict=True))
    )
    assert [r.source_local for r in records] == [LOCAL + timedelta(minutes=m) for m in (1, 2, 3)]
    assert records[1].values["T상전압"] == 227.0
    # Two different values for one channel at one timestamp cannot be chosen between.
    assert (conflicts, records[0].values["R상전압"]) == (1, None)
    assert aihub_replay.replay_offsets(records, 60.0) == (0.0, 1.0, 2.0)


def test_selection_rejects_other_devices_and_empty_ranges(tmp_path):
    archive = _archive(tmp_path)
    wrong = dataclasses.replace(BINDING, device_id="1")
    with pytest.raises(ValueError, match="identifiers"):
        aihub_replay.load_replay_records(_selection(archive, binding=wrong))
    with pytest.raises(ValueError, match="no observations"):
        aihub_replay.load_replay_records(
            _selection(
                archive,
                start_local=LOCAL + timedelta(hours=1),
                end_local=LOCAL + timedelta(hours=2),
            )
        )


def test_prepare_binds_only_evidenced_meanings_and_leaves_collection_stopped(tmp_path, monkeypatch):
    root = tmp_path / "replay"
    endpoint = "opc.tcp://127.0.0.1:48555/replay/"
    archive = _archive(tmp_path)
    treat_archive_as_profiled(monkeypatch, archive)
    manifest = aihub_replay.prepare(root, endpoint, _selection(archive), name="test")

    (source,) = JsonSourceRepository(root / "sources.json").list_sources()
    assert source.config.asset_id == "boiler-asset"
    assert [m.node_id for m in source.config.node_mappings] == [
        aihub_replay.node_id(channel) for channel in manifest["channels"]
    ]
    bound = {b.channel_id: b for b in source.config.semantic_bindings}
    # Power has no evidenced unit in the AI-Hub dictionary and stays unresolved.
    assert set(bound) == {"R상전압", "S상전압", "T상전압"}
    assert bound["R상전압"].version == AIHUB_239_SEMANTICS_V3
    assert bound["R상전압"].definition.unit == "V"
    (control,) = SqliteCollectionControlRepository(root / "control.sqlite").list_records()
    assert control.desired_state.value == "stopped"
    assert manifest["record_count"] == 3
    with pytest.raises(ValueError, match="empty"):
        aihub_replay.prepare(root, endpoint, _selection(_archive(tmp_path)), name="test")


def test_prepare_binds_no_meaning_for_an_unprofiled_archive(tmp_path):
    root = tmp_path / "replay"
    endpoint = "opc.tcp://127.0.0.1:48555/replay/"
    manifest = aihub_replay.prepare(root, endpoint, _selection(_archive(tmp_path)), name="test")

    (source,) = JsonSourceRepository(root / "sources.json").list_sources()
    assert source.config.semantic_bindings == ()
    assert manifest["bound_channels"] == []
    assert manifest["channels"]


def test_server_keeps_unpublished_channel_non_good_until_first_record(tmp_path):
    asyncua = pytest.importorskip("asyncua")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = tmp_path / "replay"
    endpoint = f"opc.tcp://127.0.0.1:{port}/replay/"
    aihub_replay.prepare(root, endpoint, _selection(_archive(tmp_path)), name="test")

    async def scenario():
        stop = asyncio.Event()
        server = asyncio.create_task(
            aihub_replay.serve(
                root,
                stop,
                speed=600.0,
                loop=False,
                freeze_after_records=0,
            )
        )
        try:
            for _ in range(100):
                if (root / aihub_replay.REPLAY_LOG).exists():
                    break
                await asyncio.sleep(0.05)
            async with asyncua.Client(endpoint) as client:
                node = client.get_node(aihub_replay.node_id("R상전압"))
                value = await node.read_data_value(raise_on_bad_status=False)
        finally:
            stop.set()
            await server
        return value

    value = asyncio.run(scenario())
    assert not value.StatusCode.is_good()


def test_server_publishes_recorded_values_on_the_replay_clock(tmp_path):
    asyncua = pytest.importorskip("asyncua")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = tmp_path / "replay"
    endpoint = f"opc.tcp://127.0.0.1:{port}/replay/"
    aihub_replay.prepare(root, endpoint, _selection(_archive(tmp_path)), name="test")

    async def scenario():
        stop = asyncio.Event()
        server = asyncio.create_task(
            aihub_replay.serve(
                root, stop, speed=600.0, loop=False, publish_ledger=root / "ledger.jsonl"
            )
        )
        try:
            for _ in range(100):
                if (root / aihub_replay.REPLAY_LOG).exists():
                    break
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.5)  # all three records at 0.1 s spacing
            async with asyncua.Client(endpoint) as client:
                node = client.get_node(aihub_replay.node_id("T상전압"))
                value = await node.read_data_value()
        finally:
            stop.set()
            await server
        return value

    value = asyncio.run(scenario())
    (log,) = [
        json.loads(line) for line in (root / aihub_replay.REPLAY_LOG).read_text().splitlines()
    ]
    started = datetime.fromisoformat(log["replay_started_at"])
    assert value.Value.Value == 228.0  # the last selected record, unchanged
    # Time is rebased: last record is 2 recorded minutes after the first, at 600x.
    assert value.SourceTimestamp.replace(tzinfo=UTC) - started == timedelta(seconds=0.2)
    assert log["source_start_local"] == (LOCAL + timedelta(minutes=1)).isoformat()
    ledger = [json.loads(line) for line in (root / "ledger.jsonl").read_text().splitlines()]
    assert len(ledger) == 3 and len({entry["run"] for entry in ledger}) == 1
    assert ledger[-1]["values"]["T상전압"] == 228.0
    assert ledger[-1]["good"]["T상전압"] is True


def test_prepare_records_an_optional_asset_display_name_without_changing_identity(tmp_path):
    root = tmp_path / "replay"
    aihub_replay.prepare(
        root,
        "opc.tcp://127.0.0.1:48555/replay/",
        _selection(_archive(tmp_path)),
        name="test",
        asset_display_name="보일러 · reference asset",
    )

    (source,) = JsonSourceRepository(root / "sources.json").list_sources()
    assert source.config.asset_display_name == "보일러 · reference asset"
    assert source.asset_id == "boiler-asset"
