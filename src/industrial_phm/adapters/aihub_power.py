"""Streaming reader for AI-Hub 239 raw power observations, without alignment."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path
from zipfile import ZipFile


@dataclass(frozen=True, slots=True)
class PowerObservation:
    """Source identity and raw local time are deliberately not asset/time bindings."""

    member: str
    record_index: int
    device_id: str
    device_board_id: str
    channel_name: str
    timestamp_text: str
    value: float | None
    raw_record_json: str


def archive_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def list_power_members(path: Path) -> tuple[str, ...]:
    with ZipFile(path) as archive:
        members = tuple(sorted(n for n in archive.namelist() if n.endswith(".json")))
    if not members or len(members) != len(set(members)):
        raise ValueError("archive must contain uniquely named JSON members")
    return members


def iter_power_observations(path: Path, member: str) -> Iterator[PowerObservation]:
    """Read one observed source schema with bounded memory; never extract ZIP paths.

    The two device identifiers must precede the data array, as in the profiled
    archives. Unknown layouts fail explicitly rather than guess an identity.
    """
    try:
        ijson = importlib.import_module("ijson")
    except ModuleNotFoundError as error:
        raise RuntimeError("AI-Hub reader requires the 'aihub' extra") from error
    with ZipFile(path) as archive:
        if archive.namelist().count(member) != 1:
            raise ValueError("member must identify exactly one archive entry")
        header: dict[str, str] = {}
        found_data = False
        with archive.open(member) as stream:
            for prefix, event, value in ijson.parse(stream, use_float=True):
                if prefix == "data" and event == "start_array":
                    found_data = True
                    break
                if prefix in {"DEVICE_ID", "DEVICE_BD_ID"} and event in {"string", "number"}:
                    if isinstance(value, bool) or not isinstance(value, (str, int)):
                        raise ValueError("device identifiers must be strings or integers")
                    header[prefix] = str(value)
        if (
            not found_data
            or set(header) != {"DEVICE_ID", "DEVICE_BD_ID"}
            or not all(header.values())
        ):
            raise ValueError("DEVICE_ID and DEVICE_BD_ID must precede the data array")
        with archive.open(member) as stream:
            for index, raw in enumerate(ijson.items(stream, "data.item", use_float=True)):
                if not isinstance(raw, dict) or not {
                    "ITEM_NAME",
                    "ITEM_VALUE",
                    "TIMESTAMP",
                }.issubset(raw):
                    raise ValueError(f"invalid observation at {member}:{index}")
                name, timestamp, value = raw["ITEM_NAME"], raw["TIMESTAMP"], raw["ITEM_VALUE"]
                if not isinstance(name, str) or not name.strip() or name != name.strip():
                    raise ValueError(f"invalid ITEM_NAME at {member}:{index}")
                if not isinstance(timestamp, str):
                    raise ValueError(f"invalid TIMESTAMP at {member}:{index}")
                parsed = datetime.fromisoformat(timestamp)
                if len(timestamp) != 19 or timestamp[10] != " " or parsed.tzinfo is not None:
                    raise ValueError(f"noncanonical raw timestamp at {member}:{index}")
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                ):
                    raise ValueError(f"invalid ITEM_VALUE at {member}:{index}")
                yield PowerObservation(
                    member=member,
                    record_index=index,
                    device_id=header["DEVICE_ID"],
                    device_board_id=header["DEVICE_BD_ID"],
                    channel_name=name,
                    timestamp_text=timestamp,
                    value=None if value is None else float(value),
                    raw_record_json=json.dumps(raw, ensure_ascii=False, sort_keys=True),
                )
