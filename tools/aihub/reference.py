"""Prepare a small recorded three-phase CSV with explicit source/time provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from industrial_phm.adapters.aihub_power import archive_sha256, iter_power_observations
from industrial_phm.adapters.aihub_power_history import (
    AIHUB_239_SEMANTICS_V3,
    PowerHistoryBinding,
    channel_definition,
    semantics_dictionary_digest,
)


def prepare_reference(
    archive: Path,
    member: str,
    binding: PowerHistoryBinding,
    start: datetime,
    end: datetime,
    output: Path,
) -> dict[str, object]:
    """Export recorded values only; reject conflicts or unconfirmed physical meaning."""
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        raise ValueError("selection needs increasing source-local naive timestamps")
    digest = archive_sha256(archive)
    channels = tuple(f"{phase}상전압" for phase in "RST")
    definitions = {
        channel: channel_definition(
            AIHUB_239_SEMANTICS_V3, channel, archive_sha256=digest, member=member
        )
        for channel in channels
    }
    if any(definition.unit not in {"V", "A"} for definition in definitions.values()):
        raise ValueError(
            "reference channels need confirmed semantics in the profiled archive scope"
        )
    grouped: dict[str, dict[str, float | None]] = {}
    indices: dict[str, dict[str, int]] = {}
    for record in iter_power_observations(archive, member):
        if (record.device_id, record.device_board_id) != (
            binding.device_id,
            binding.device_board_id,
        ):
            raise ValueError("source identifiers do not match binding")
        if not start <= datetime.fromisoformat(record.timestamp_text) < end:
            continue
        if record.channel_name not in channels:
            continue
        values = grouped.setdefault(record.timestamp_text, {})
        if record.channel_name in values:
            raise ValueError(
                "duplicate timestamp/channel must be resolved explicitly before CSV export"
            )
        values[record.channel_name] = record.value
        indices.setdefault(record.timestamp_text, {})[record.channel_name] = record.record_index
    if not grouped or any(set(values) != set(channels) for values in grouped.values()):
        raise ValueError(
            "selected timestamps must have all three voltage channels; no filling or interpolation"
        )
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "recorded-phase.csv"
    timezone = ZoneInfo(binding.timezone)
    fields = [
        "timestamp",
        *channels,
        "source_timestamp_local",
        "archive_sha256",
        "source_member",
        "device_id",
        "device_board_id",
        "timezone_evidence",
        "source_record_indices",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for at, values in sorted(grouped.items()):
            writer.writerow(
                {
                    "timestamp": datetime.fromisoformat(at)
                    .replace(tzinfo=timezone)
                    .astimezone(UTC)
                    .isoformat(),
                    **{
                        channel: "" if value is None else value for channel, value in values.items()
                    },
                    "source_timestamp_local": at,
                    "archive_sha256": digest,
                    "source_member": member,
                    "device_id": binding.device_id,
                    "device_board_id": binding.device_board_id,
                    "timezone_evidence": binding.timezone_evidence,
                    "source_record_indices": json.dumps(
                        indices[at], ensure_ascii=False, sort_keys=True
                    ),
                }
            )
    phase_lines = []
    for channel, definition in definitions.items():
        quantity = "voltage" if definition.unit == "V" else "current"
        unit_evidence = (
            f"AI-Hub239 {AIHUB_239_SEMANTICS_V3}; "
            f"guide 1.6.3 and recorded phase relation; {definition.unit}"
        )
        interpretation = (
            f"SHA256={digest}; {channel[0]}; TZ={binding.timezone} assumed; "
            "source timezone unverified"
        )
        if len(unit_evidence) > 128 or len(interpretation) > 128:
            raise ValueError("binding evidence exceeds the bounded Web field size")
        phase_lines.append(f"{channel},{quantity},{channel[0]},{unit_evidence},{interpretation}")
    (output / "phase-bindings.txt").write_text("\n".join(phase_lines) + "\n", encoding="utf-8")
    report: dict[str, object] = {
        "kind": "derived-recorded-csv-not-current-equipment",
        "archive_path": str(archive.resolve()),
        "archive_sha256": digest,
        "member": member,
        "binding": asdict(binding),
        "source_timezone_verified": False,
        "start_local_inclusive": start.isoformat(),
        "end_local_exclusive": end.isoformat(),
        "row_count": len(grouped),
        "channels": list(channels),
        "null_values": sum(v is None for values in grouped.values() for v in values.values()),
        "channel_definitions": {channel: asdict(value) for channel, value in definitions.items()},
        "semantics_version": AIHUB_239_SEMANTICS_V3,
        "semantics_dictionary_sha256": semantics_dictionary_digest(AIHUB_239_SEMANTICS_V3),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "source_record_indices": indices,
    }
    (output / "provenance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--member", required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binding = PowerHistoryBinding(**json.loads(args.binding.read_text(encoding="utf-8")))
    report = prepare_reference(
        args.archive, args.member, binding, args.start, args.end, args.output
    )
    print(f"Prepared {report['row_count']} recorded rows: {args.output / 'recorded-phase.csv'}")


if __name__ == "__main__":
    main()
