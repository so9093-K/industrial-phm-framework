"""Explicit local full-archive profiling; raw payloads never enter the repository."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from industrial_phm.adapters.aihub_power import (
    archive_sha256,
    iter_power_observations,
    list_power_members,
)


def profile_archive(path: Path) -> dict[str, object]:
    members = []
    with tempfile.TemporaryDirectory(prefix="phm-profile-") as temp:
        db = sqlite3.connect(Path(temp) / "profile.sqlite")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA cache_size=-32768")
        try:
            for member in list_power_members(path):
                db.execute("DROP TABLE IF EXISTS observation")
                db.execute("CREATE TABLE observation (timestamp TEXT, channel TEXT, value REAL)")
                names: Counter[str] = Counter()
                nulls: Counter[str] = Counter()
                identities = set()
                batch = []
                for record in iter_power_observations(path, member):
                    names[record.channel_name] += 1
                    if record.value is None:
                        nulls[record.channel_name] += 1
                    identities.add((record.device_id, record.device_board_id))
                    batch.append((record.timestamp_text, record.channel_name, record.value))
                    if len(batch) == 10000:
                        db.executemany("INSERT INTO observation VALUES (?, ?, ?)", batch)
                        batch.clear()
                db.executemany("INSERT INTO observation VALUES (?, ?, ?)", batch)
                db.commit()
                db.execute("CREATE INDEX IF NOT EXISTS obs_key ON observation(timestamp, channel)")
                duplicates, conflicts = db.execute("""
                    SELECT coalesce(sum(n - 1), 0), coalesce(sum(variants > 1), 0)
                    FROM (SELECT count(*) n,
                        count(DISTINCT value) + (count(*) > count(value)) variants
                        FROM observation GROUP BY timestamp, channel HAVING count(*) > 1)
                """).fetchone()
                start, end = db.execute(
                    "SELECT min(timestamp), max(timestamp) FROM observation"
                ).fetchone()
                coverage = db.execute("""
                    SELECT n, count(*) FROM (
                        SELECT timestamp, count(DISTINCT channel) n
                        FROM observation GROUP BY timestamp
                    ) GROUP BY n ORDER BY n
                """).fetchall()
                # Source-local cadence distribution, not an aggregation-window claim.
                cadence = db.execute("""
                    SELECT delta, count(*) FROM (
                        SELECT unixepoch(timestamp) - lag(unixepoch(timestamp)) OVER (
                            PARTITION BY channel ORDER BY timestamp) delta
                        FROM (SELECT DISTINCT timestamp, channel FROM observation)
                    ) WHERE delta IS NOT NULL GROUP BY delta ORDER BY count(*) DESC LIMIT 10
                """).fetchall()
                members.append(
                    {
                        "member": member,
                        "record_count": sum(names.values()),
                        "source_identifiers": sorted(identities),
                        "channels": dict(sorted(names.items())),
                        "nulls": dict(sorted(nulls.items())),
                        "duplicate_extra_records": duplicates,
                        "conflicting_timestamp_channel_groups": conflicts,
                        "local_start": start,
                        "local_end": end,
                        "channels_per_timestamp": coverage,
                        "top_channel_cadence_seconds": cadence,
                    }
                )
                print(f"profiled {member}: {sum(names.values())} records", flush=True)
        finally:
            db.close()
    with ZipFile(path) as archive:
        uncompressed = sum(i.file_size for i in archive.infolist())
    return {
        "schema_version": 1,
        "archive": path.name,
        "sha256": archive_sha256(path),
        "archive_bytes": path.stat().st_size,
        "uncompressed_bytes": uncompressed,
        "scope": "all JSON members in this archive; not a dataset-wide guarantee",
        "timezone": None,
        "units": None,
        "members": members,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = profile_archive(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
