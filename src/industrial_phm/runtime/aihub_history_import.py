"""Import one explicit AI-Hub 239 member/time selection into common Asset History."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from industrial_phm.adapters.aihub_power import archive_sha256, iter_power_observations
from industrial_phm.adapters.aihub_power_history import (
    AIHUB_239_HISTORY_SCHEMA,
    AIHUB_239_SEMANTICS_DIGESTS,
    AIHUB_239_SEMANTICS_V3,
    PowerHistoryBinding,
    project_power_observation,
)
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory


def selection_identity(
    archive_digest: str,
    member: str,
    binding: PowerHistoryBinding,
    start: datetime,
    end: datetime,
    batch_size: int,
) -> tuple[dict[str, object], str]:
    """Return the selection record and its id; the metadata schema is not part of it."""
    selection: dict[str, object] = {
        "archive_sha256": archive_digest,
        "member": member,
        "binding": asdict(binding),
        "start_local": start.isoformat(),
        "end_local": end.isoformat(),
        "batch_size": batch_size,
    }
    selection_id = hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()
    return selection, selection_id


def batch_id(selection_id: str, index: int) -> str:
    return f"aihub239:{selection_id}:{index}"


def _selected_batches(
    archive: Path,
    member: str,
    binding: PowerHistoryBinding,
    start: datetime,
    end: datetime,
    batch_size: int,
    digest: str,
) -> Iterator[list[FileBackfillEvent]]:
    archive_bytes = archive.stat().st_size
    batch: list[FileBackfillEvent] = []
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
            yield batch
            batch = []
    if batch:
        yield batch


def holds_selection(
    archive: Path,
    member: str,
    binding: PowerHistoryBinding,
    start: datetime,
    end: datetime,
    history: DuckLakeAssetHistory,
    *,
    batch_size: int = 2000,
    archive_digest: str | None = None,
) -> bool:
    """Whether ``history`` already holds this selection's first batch from these archive bytes.

    Batch IDs carry the archive digest, so a stream filled from other bytes of the same member
    never qualifies. This is what lets a stream stored without a source version take one.

    Args:
        archive: AI-Hub 239 ZIP archive.
        member: JSON member inside ``archive``.
        binding: The binding the stream was imported with, including its source ID.
        start: Inclusive naive source-local selection start.
        end: Exclusive naive source-local selection end.
        history: Asset history to look in.
        batch_size: Batch size the stream was imported with.
        archive_digest: SHA-256 of ``archive`` when the caller already has it.

    Returns:
        True when the first batch is stored identically under the same selection.
    """
    digest = archive_digest or archive_sha256(archive)
    _, selection_id = selection_identity(digest, member, binding, start, end, batch_size)
    first = next(_selected_batches(archive, member, binding, start, end, batch_size, digest), None)
    if first is None:
        return False
    return history.get_file_batch_commit(first, batch_id=batch_id(selection_id, 0)) is not None


def import_history(
    archive: Path,
    member: str,
    binding: PowerHistoryBinding,
    start: datetime,
    end: datetime,
    history: DuckLakeAssetHistory,
    *,
    batch_size: int = 2000,
    flush_every_batches: int = 10,
    progress: Callable[[int], None] | None = None,
) -> dict[str, object]:
    """Use local source time for selection; normalize only with the explicit binding.

    Exact reruns recover commits. Overlapping selections with different batch
    boundaries fail on existing raw identity; they never silently duplicate rows.
    Newly appended rows are flushed from the SQLite catalog to Parquet every
    flush_every_batches batches and at the end; recovered batches need no flush.
    ``progress`` receives the number of observations written or recovered so far.
    """
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        raise ValueError("selection must be an increasing naive source-local time range")
    if isinstance(batch_size, bool) or not 1 <= batch_size <= 10000:
        raise ValueError("batch_size must be between 1 and 10000")
    if isinstance(flush_every_batches, bool) or not 1 <= flush_every_batches <= 10000:
        raise ValueError("flush_every_batches must be between 1 and 10000")
    digest = archive_sha256(archive)
    selection, selection_id = selection_identity(digest, member, binding, start, end, batch_size)
    count, batches, recovered, unflushed, flushed_rows = 0, 0, 0, 0, 0

    def flush() -> None:
        nonlocal unflushed, flushed_rows
        flushed_rows += history.flush_inlined_data().flushed_row_count
        unflushed = 0

    def commit(batch: list[FileBackfillEvent]) -> None:
        nonlocal count, batches, recovered, unflushed
        current = batch_id(selection_id, batches)
        existing = history.get_file_batch_commit(batch, batch_id=current)
        if existing is not None:
            recovered += 1
        else:
            history.append_file_batch(batch, batch_id=current)
            unflushed += 1
        count += len(batch)
        batches += 1
        if unflushed >= flush_every_batches:
            flush()
        if progress is not None:
            progress(count)

    for batch in _selected_batches(archive, member, binding, start, end, batch_size, digest):
        commit(batch)
    if unflushed:
        flush()
    # The result states which interpretation was written.
    semantics = {
        "semantic_binding_version": AIHUB_239_SEMANTICS_V3,
        "semantic_dictionary_sha256": AIHUB_239_SEMANTICS_DIGESTS[AIHUB_239_SEMANTICS_V3],
    }
    return {
        **selection,
        "metadata_schema": f"aihub-239-history-{AIHUB_239_HISTORY_SCHEMA}",
        **semantics,
        "event_count": count,
        "batch_count": batches,
        "recovered_batch_count": recovered,
        # Includes other catalog tables that were still inlined at flush time.
        "flushed_row_count": flushed_rows,
        "snapshot_id": history.current_snapshot_id(),
    }
