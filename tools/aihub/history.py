"""Import one explicit AI-Hub member/time selection into common Asset History."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from industrial_phm.adapters.aihub_power import archive_sha256, iter_power_observations
from industrial_phm.adapters.aihub_power_history import (
    PowerHistoryBinding,
    project_power_observation,
)
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig


def import_history(
    archive: Path,
    member: str,
    binding: PowerHistoryBinding,
    start: datetime,
    end: datetime,
    history: DuckLakeAssetHistory,
    *,
    batch_size: int = 2000,
) -> dict[str, object]:
    """Use local source time for selection; normalize only with the explicit binding.

    Exact reruns recover commits. Overlapping selections with different batch
    boundaries fail on existing raw identity; they never silently duplicate rows.
    """
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        raise ValueError("selection must be an increasing naive source-local time range")
    if isinstance(batch_size, bool) or not 1 <= batch_size <= 10000:
        raise ValueError("batch_size must be between 1 and 10000")
    digest = archive_sha256(archive)
    archive_bytes = archive.stat().st_size
    selection = {
        "archive_sha256": digest,
        "member": member,
        "binding": asdict(binding),
        "start_local": start.isoformat(),
        "end_local": end.isoformat(),
        "batch_size": batch_size,
    }
    selection_id = hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()
    batch: list[FileBackfillEvent] = []
    count, batches, recovered = 0, 0, 0

    def commit() -> None:
        nonlocal count, batches, recovered
        batch_id = f"aihub239:{selection_id}:{batches}"
        existing = history.get_file_batch_commit(batch, batch_id=batch_id)
        if existing is not None:
            recovered += 1
        else:
            history.append_file_batch(batch, batch_id=batch_id)
        count += len(batch)
        batches += 1
        batch.clear()

    for record in iter_power_observations(archive, member):
        if (record.device_id, record.device_board_id) != (
            binding.device_id,
            binding.device_board_id,
        ):
            raise ValueError("member source identifiers do not match the explicit binding")
        local = datetime.fromisoformat(record.timestamp_text)
        if not start <= local < end:
            continue
        batch.append(
            project_power_observation(
                record,
                archive=archive,
                archive_digest=digest,
                archive_bytes=archive_bytes,
                binding=binding,
            )
        )
        if len(batch) == batch_size:
            commit()
    if batch:
        commit()
    return {
        **selection,
        "event_count": count,
        "batch_count": batches,
        "recovered_batch_count": recovered,
        "snapshot_id": history.current_snapshot_id(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--member", required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    parser.add_argument("--ducklake-catalog", type=Path, required=True)
    parser.add_argument("--ducklake-data", type=Path, required=True)
    args = parser.parse_args()
    try:
        binding = PowerHistoryBinding(**json.loads(args.binding.read_text()))
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=args.ducklake_catalog,
                data_path=args.ducklake_data,
            )
        )
        result = import_history(args.archive, args.member, binding, args.start, args.end, history)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
