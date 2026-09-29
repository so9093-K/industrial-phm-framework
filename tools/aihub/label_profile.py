"""Explicit local profiling of AI-Hub 239 labeling archives; payloads never enter the repository.

Each labeling member repeats observation records with a LABEL_NAME and carries
provider equipment metadata in its header. The profile records what is observed,
not what the labels or metadata mean. Labels are research-only provider
annotations; production analysis never reads this archive.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from industrial_phm.adapters.aihub_power import archive_sha256

# Masked contact information is not needed to profile the measurement data.
_EXCLUDED_HEADER_KEYS = frozenset({"KEPCO_INFO"})


def _member_header(archive: ZipFile, member: str, ijson: Any) -> dict[str, object]:
    header: dict[str, object] = {}
    with archive.open(member) as stream:
        for prefix, event, value in ijson.parse(stream, use_float=True):
            if prefix == "data" and event == "start_array":
                return header
            if (
                prefix
                and "." not in prefix
                and prefix not in _EXCLUDED_HEADER_KEYS
                and event in {"string", "number", "null", "boolean"}
            ):
                header[prefix] = value
    raise ValueError(f"{member} has no data array")


def profile_member(archive: ZipFile, member: str, ijson: Any) -> dict[str, object]:
    header = _member_header(archive, member, ijson)
    labels: Counter[str] = Counter()
    items: Counter[str] = Counter()
    nulls: Counter[str] = Counter()
    value_range: dict[str, list[float]] = {}
    labels_at: dict[str, set[str]] = defaultdict(set)
    first = last = None
    transitions = 0
    previous_label: str | None = None
    with archive.open(member) as stream:
        for record in ijson.items(stream, "data.item", use_float=True):
            item, value = record["ITEM_NAME"], record["ITEM_VALUE"]
            label, timestamp = record.get("LABEL_NAME"), record["TIMESTAMP"]
            items[item] += 1
            labels[str(label)] += 1
            if value is None:
                nulls[item] += 1
            else:
                bounds = value_range.setdefault(item, [value, value, 0.0])
                bounds[0], bounds[1] = min(bounds[0], value), max(bounds[1], value)
                bounds[2] += value
            labels_at[timestamp].add(str(label))
            first = timestamp if first is None else min(first, timestamp)
            last = timestamp if last is None else max(last, timestamp)
            if previous_label is not None and label != previous_label:
                transitions += 1
            previous_label = label
    return {
        "member": member,
        "header": header,
        "record_count": sum(items.values()),
        "timestamp_count": len(labels_at),
        "start": first,
        "end": last,
        "label_counts": dict(labels.most_common()),
        "timestamps_with_multiple_labels": sum(len(v) > 1 for v in labels_at.values()),
        "record_order_label_transitions": transitions,
        "item_counts": dict(sorted(items.items())),
        "null_counts": dict(sorted(nulls.items())),
        "value_ranges": {
            item: {
                "min": low,
                "max": high,
                "mean": total / (items[item] - nulls[item]),
            }
            for item, (low, high, total) in sorted(value_range.items())
        },
    }


def profile_label_archive(path: Path) -> dict[str, object]:
    try:
        ijson = importlib.import_module("ijson")
    except ModuleNotFoundError as error:
        raise RuntimeError("label profiling requires the 'aihub' extra") from error
    with ZipFile(path) as archive:
        members = sorted(n for n in archive.namelist() if n.endswith(".json"))
        if not members or len(members) != len(set(members)):
            raise ValueError("archive must contain uniquely named JSON members")
        profiles = [profile_member(archive, member, ijson) for member in members]
    return {
        "archive": path.name,
        "archive_sha256": archive_sha256(path),
        "member_count": len(members),
        "members": profiles,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = profile_label_archive(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"profiled {result['member_count']} members -> {args.output}")


if __name__ == "__main__":
    main()
