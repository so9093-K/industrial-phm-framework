# History live retention evidence

Measured: 2026-10-07
Runtime: CPython 3.14.7, DuckDB 1.5.5, DuckLake d8a1881e, macOS 27.0.1 arm64, base revision
`497ea93` with the working-tree changes described below. Single local runs; not capacity
guarantees.

## Question

How long does one `maintenance history retain` run hold the local catalog lease, and does that
grow with the stored state? Every collector append waits for the same lease and fails after
10 seconds ([ADR-0023](../adr/0023-retain-live-evidence-for-a-bounded-period.md)).

## Method

`tools/history/retention_profile.py` prepares N live commits in an isolated catalog, each with a
fixed number of rows copied from one public live batch and the same commit metadata shape, one
second of event time apart. Every k-th commit is older than the cutoff. It then runs retention once,
recording every lease hold, and measures a public append before and after. The cutoff is taken
after the last prepared commit, so one run expires a backlog of all N snapshots: the worst case.
State size is varied by N and rows per commit, not by collecting for a period.

Live collection was measured at about 90 events per commit and 53 commits per minute in the
accelerated Phase 10 replay; the AI-Hub reference cadence is 35 events per minute per asset.

## Results before the change (single delete, single expiry)

One row per commit, half of the rows old:

| Snapshots N | Delete step hold | Expiry + cleanup hold | Append before → after | Catalog-inlined rows after run |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 72 ms | 95 ms | 66 → 71 ms | 3,002 |
| 5,000 | 114 ms | 306 ms | 70 → 71 ms | 15,002 |
| 20,000 | 303 ms | 1,115 ms | 116 → 72 ms | 60,002 |
| 50,000 | 678 ms | 2,778 ms | 151 → 71 ms | 150,002 |

Ninety rows per commit (Parquet files), half old: the delete step held the lease 528 ms at
180,000 stored rows and 2,059 ms at 720,000.

Interpretation:

- Expiry holds the lease about 55 µs per expired snapshot. A daily run at the Phase 10 rate
  (about 76,000 commits) would hold it about 4 s; a one-week backlog about 30 s.
- The delete step grows with the rows it deletes and, because its time predicate could not be
  pruned by file statistics, with the stored rows. At the Phase 10 rate a daily run deletes millions
  of rows, far past the lease timeout.
- Stored snapshots slow appends (66 → 151 ms from 1,000 to 50,000); retention restores them.
- Deleted catalog-inlined rows stay in the catalog after expiry; a flush empties them (0 rows).

## Change

- Deletion selects rows with prunable predicates (`event_at` range, or `ingested_at` range for rows
  without an event time) and runs in event-time slices of at most 100,000 rows on whole minutes,
  one lease and one commit per slice. Ingestion-batch rows are forgotten when every recorded event
  of the batch has been deleted, counted across slices; a batch that also lost rows in an earlier
  run is checked once by its stored rows.
- Snapshots are expired in chunks of 2,000, one lease each.
- A final flush purges deleted catalog-inlined rows.

## Results after the change

| State | Longest lease hold | Delete slices | Expiry chunks |
| --- | ---: | --- | --- |
| 5,000 snapshots, 1 row per commit | 126 ms | — | 118–126 ms |
| 20,000 snapshots, 1 row per commit | 336 ms (delete, before slicing) | — | 117–139 ms |
| 720,000 rows (8,000 × 90), half old | 604 ms | 4 × 518–604 ms | 122–380 ms |

With prunable predicates alone (one delete), the same 720,000-row state held 1,592 ms deleting half
the rows and 807 ms deleting a tenth: about 2.7 µs per deleted row plus a fixed part. Slicing turns
that into a bound per lease. Catalog-inlined rows are 0 after every run.

## Interpretation

The change splits the two steps that dominated: deletion into slices of about 100,000 rows (a
minute holding more rows is one slice, so the bound follows the data rate) and expiry into chunks
of 2,000 snapshots. It is not a bound independent of state size. Four leases still read state that
grows with it; in the 720,000-row, 8,009-snapshot run they held:

| Lease | Hold |
| --- | ---: |
| Slice discovery (minute histogram of rows before the cutoff) | 184 ms |
| Snapshot listing | 74 ms |
| Cleanup (2,182 files) | 134 ms |
| Final flush | 69 ms |

Cleanup removing 8,000 files held 549 ms in an earlier run. These grow with the backlog read,
the snapshot count and the files removed, but in the measured workload stayed well below the
delete slices. The total run time also grows with what it removes (4.6 s for 360,000 rows and 8,009
snapshots), during which appends interleave between leases.

Space from rows a run deletes is freed once no retained snapshot references them. In this profile
only the first slice's files were removed (2,182 of 8,000), because the run's own later slice
commits are newer than the cutoff; the next run frees the rest. In operation, collector commits
keep every recent snapshot, so deleted files are freed about one retention period after deletion,
as ADR-0023 states.

## Limitations

- Prepared rows are copies with regular timestamps; the per-row cost depends on file layout, and
  a merge-compacted layout was not profiled here.
- One host and one process at a time; lease holds bound waits only on this local lock.
- The catalog file itself does not shrink (no VACUUM); SQLite reuses freed pages.

Reports: `artifacts/retention-profile-before/`, `artifacts/retention-profile-after/` (generated local
artifacts).
