"""Audit stored OPC UA history against the replay publish ledger.

The replay ledger is ground truth for what the server wrote. A subscription is
expected to deliver every write whose value or status changed on that node within
one server run (the first write of a run is a change from BadWaitingForInitialData).
Stored raw events are classified as expected deliveries, re-deliveries of the
current value (a subscription's initial notification), unknown, or duplicates, and
expected deliveries that were never stored are reported as gaps.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

Key = tuple[str, datetime]


@dataclass(frozen=True, slots=True)
class LedgerTruth:
    writes: dict[Key, float | None]
    expected: frozenset[Key]


def load_ledger(path: Path) -> LedgerTruth:
    writes: dict[Key, float | None] = {}
    expected: set[Key] = set()
    previous: dict[tuple[str, str], tuple[bool, float | None]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            entry = json.loads(line)
            at = datetime.fromisoformat(entry["at"])
            for channel, value in entry["values"].items():
                key = (channel, at)
                writes[key] = value
                state = (value is not None, value)
                if previous.get((entry["run"], channel)) != state:
                    expected.add(key)
                previous[(entry["run"], channel)] = state
    return LedgerTruth(writes, frozenset(expected))


def _gaps(missing: list[datetime], *, join: timedelta) -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    for at in sorted(missing):
        if gaps and at - gaps[-1]["_end"] <= join:  # type: ignore[operator]
            gaps[-1]["_end"] = at
            gaps[-1]["events"] = int(gaps[-1]["events"]) + 1  # type: ignore[call-overload]
        else:
            gaps.append({"_start": at, "_end": at, "events": 1})
    return [
        {
            "start": gap["_start"].isoformat(),  # type: ignore[attr-defined]
            "end": gap["_end"].isoformat(),  # type: ignore[attr-defined]
            "events": gap["events"],
        }
        for gap in gaps
    ]


def audit(
    truth: LedgerTruth,
    observed: list[tuple[str, datetime | None, object]],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    gap_join: timedelta = timedelta(seconds=5),
) -> dict[str, object]:
    def inside(at: datetime) -> bool:
        return (since is None or at >= since) and (until is None or at < until)

    counts: Counter[Key] = Counter()
    mismatched = 0
    unknown = 0
    no_timestamp = 0
    for channel, at, value in observed:
        if at is None:
            no_timestamp += 1
            continue
        if not inside(at):
            continue
        key = (channel, at)
        counts[key] += 1
        if key not in truth.writes:
            unknown += 1
        elif truth.writes[key] is not None and value != truth.writes[key]:
            mismatched += 1
    expected = {key for key in truth.expected if inside(key[1])}
    delivered = expected & counts.keys()
    missing = sorted(expected - counts.keys(), key=lambda key: key[1])
    redelivered = sum(1 for key in counts if key in truth.writes and key not in truth.expected)
    return {
        "window": {
            "since": None if since is None else since.isoformat(),
            "until": None if until is None else until.isoformat(),
        },
        "expected_deliveries": len(expected),
        "delivered": len(delivered),
        "missing": len(missing),
        "missing_ratio": round(len(missing) / len(expected), 6) if expected else 0.0,
        "duplicate_keys": sum(1 for count in counts.values() if count > 1),
        "redelivered_current_values": redelivered,
        "unknown_events": unknown,
        "value_mismatches": mismatched,
        "events_without_source_timestamp": no_timestamp,
        "gaps": _gaps([key[1] for key in missing], join=gap_join),
    }


def observed_events(root: Path, source_id: str) -> list[tuple[str, datetime | None, object]]:
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(root / "catalog.sqlite", root / "data")
    )
    result = []
    for event in history.query_opcua_events(source_id):
        observation = event.event.notification.observation
        result.append((observation.channel_id, observation.source_timestamp, observation.value))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--since", type=datetime.fromisoformat)
    parser.add_argument("--until", type=datetime.fromisoformat)
    args = parser.parse_args()
    report = audit(
        load_ledger(args.ledger),
        observed_events(args.root, args.source_id),
        since=args.since,
        until=args.until,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
