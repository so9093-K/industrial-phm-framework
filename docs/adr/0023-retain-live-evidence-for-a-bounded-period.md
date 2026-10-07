# 0023. Retain live evidence for a bounded period, except open-review evidence

Status: Accepted

## Context

Live OPC UA collection grows DuckLake history, its snapshots and the finalized-window store without
bound. Merge-only compaction keeps every replaced file because no snapshot is ever expired, and
`windows.sqlite` keeps every finalized window payload. The representative-size measurement (#316)
sizes stored history at about 243 B per observation, and the product requirement is to keep recent
live evidence, by default the last week, with exceptions. Recovery of deleted evidence is not
required.

Three facts constrain what may be deleted:

- Explicitly imported FILE history uses source event times that can be years old; an event-time
  policy would delete it on import.
- An analysis result references its input: a finalized window for live analysis
  ([ADR-0008](0008-analyze-finalized-window-accepted-events.md)) or a fixed history snapshot for
  historical analysis. A reviewer of an open review request needs that evidence.
- The live analysis runner reads finalized windows after a durable per-policy cursor; a window it
  has not passed is still pending work.

## Decision

- The retention unit is **live evidence by event time**: OPC UA raw/history rows (receive time when
  the event time is unknown) and finalized windows. The default period is seven days.
- FILE history is excluded. It is deleted only by an explicit future decision, not by this policy.
- Evidence of every human review request that is not closed is protected: the analysis run's
  observed source range, its finalized window and its history snapshot. Protection ends when the
  review closes. A review request whose result cannot be found aborts the run before any deletion.
- A finalized window is deleted only after every recorded analysis cursor has passed it. Skipped
  outcomes are deleted before their windows, so an interruption leaves no skip without a window.
- History snapshots taken before the cutoff are expired except the current and protected ones, and
  files no remaining snapshot references are removed. Time travel is therefore available for the
  same period as the data.
- A batch whose live rows were all deleted is forgotten; a late exact retry stores it again and the
  next run deletes it. A retry of a batch with rows left but an expired commit snapshot fails
  explicitly rather than writing a duplicate.
- Retention is an explicit maintenance command, `maintenance history retain <workspace>`, with a
  dry run. It uses the same catalog lease as writers, one step at a time. Automatic scheduling is a
  separate deployment decision.
- Files are not rewritten. DuckLake `ducklake_rewrite_data_files` (extension `d8a1881e`, DuckDB
  1.5.5) was observed to change the values that earlier snapshots return for rows deleted from
  flushed files (BIGINT `event_index`/`collection_index` 0 → 256), which would corrupt protected
  evidence. Delete, expire, cleanup and merge-only compaction left those snapshots unchanged in the
  same reproduction.

## Consequences

Live storage is bounded by the retention period instead of growing forever, and an operator can see
what a run would delete before running it.

Physical space is reclaimed per file. Live commits above DuckLake's 10-row inlining limit are Parquet
files written in time order, so a file is removed once all its rows have passed the cutoff, also when
that happens over two runs. Deleted rows stay physically, hidden from every retained snapshot, in a
file that also holds newer or FILE rows, and in catalog-inlined rows (commits of fewer than ten
events), which DuckLake does not purge on expiry in this version. Because the snapshots of the last
period still reference rows deleted during it, live data can occupy disk for up to about twice the
retention period.

Closed reviews keep their result and judgment, but their windows, observations and input snapshots
older than the period are deleted. A historical analysis whose snapshot has expired cannot be
recomputed. Retention of `telemetry.sqlite`, the SQLite catalog file size (VACUUM) and FILE history
are not covered.

## References

- [ADR-0008](0008-analyze-finalized-window-accepted-events.md)
- [ADR-0015](0015-back-up-a-stopped-operations-workspace-as-one-recovery-unit.md)
