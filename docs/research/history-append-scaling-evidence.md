# History append scaling evidence

## Purpose

This note separates live DuckLake append cost into connection/initialization, batch identity, duplicate
evidence, commit, and recovery provenance work. File compaction is treated as a physical-maintenance
concern, while append identity and crash recovery remain a separate history contract.

These are local GitHub-hosted runner measurements, not capacity guarantees.

## Runtime

- Python 3.14.7
- DuckDB 1.5.5
- DuckLake extension `d8a1881e`
- Linux x86_64
- 35 observations per probe batch across 35 channels

`tools/history/append_profile.py` produces the repeatable report.

## Full-data N=0 / N=2,000 profile

The N=2,000 state contains 2,000 real history batches and 4,000 active data files before compaction.

| Path | N=0 | N=2,000 before compaction | N=2,000 after compaction |
| --- | ---: | ---: | ---: |
| unique append total | 0.407 s | 0.368 s | 0.345 s |
| exact retry total | 0.240 s | 0.320 s | 0.292 s |
| connect/attach, unique | 0.160 s | 0.164 s | 0.145 s |
| raw duplicate lookup, unique | 0.026 s | 0.056 s | 0.031 s |
| retry provenance scan | 0.0048 s | 0.0489 s | 0.0473 s |

Unique append does not grow from N=0 to N=2,000 in this profile. Small-file compaction also does not
materially change it. Exact retry does grow because the previous recovery path scanned every
application-authored DuckLake snapshot to find the matching batch provenance.

## N=10,000 metadata-only isolation

A separate mode creates 10,000 ingestion-batch/snapshot commits without raw/history data files. This
isolates catalog/snapshot count from Parquet/raw-row volume and avoids repeating the roughly 50-minute
full-data N=10,000 state build used by the compaction profile.

Before the indexed recovery change:

- state preparation: 153.5 s
- snapshots: 10,007
- active data files: 0
- unique append: 0.342 s
- exact retry: 0.453 s
- retry provenance scan: 0.162 s

This rules out snapshot/catalog count by itself as the main unique-append scaling cause. It identifies
the exact-retry provenance scan as the clear O(total snapshots) path.

## Implemented contract

The spool writer previously called `get_opcua_batch_commit()` and then, on a miss,
`append_opcua_batch()`, whose implementation repeated the same identity check. The writer now calls
one `append_or_recover_opcua_batch()` operation. One catalog lease therefore decides whether the
batch is new or an identical durable recovery.

Current commits also write a rebuildable SQLite accelerator adjacent to the catalog:

```text
<catalog>.phm-batch-index.sqlite
batch_id -> snapshot_id
```

The accelerator is not evidence and is not a source of truth.

- ingestion mode/event count remain in DuckLake `history.ingestion_batch`.
- fingerprint and batch provenance remain in DuckLake snapshot commit extra-info.
- the indexed snapshot ID is verified directly against the DuckLake catalog primary-key tables
  `ducklake_snapshot` and `ducklake_snapshot_changes`.
- a missing sidecar falls back to the original DuckLake provenance scan and then rebuilds the entry.
- a stale/wrong sidecar mapping fails direct source validation, falls back to DuckLake, and self-heals.
- the sidecar update happens after the DuckLake commit while the same local catalog lease is held.
  A process loss between commit and sidecar update therefore leaves durable history intact; the next
  retry rebuilds the accelerator.
- pre-upgrade/unindexed old batches may pay one full provenance scan on their first recovery.

With the indexed current-batch recovery path at N=10,000 metadata-only:

- state preparation: 135.0 s
- snapshots: 10,007
- unique append: 0.357 s
- exact retry: 0.279 s
- full `retry_provenance_scan`: absent
- direct snapshot provenance lookup: 0.009 s during retry
- process RSS after retry: about 199 MB

The exact retry reduction is about 38% relative to the unindexed N=10,000 run, while preserving
source-of-truth validation.

## Interpretation

The evidence supports three separate conclusions:

1. **Snapshot count alone is not the unique-append bottleneck.** N=10,000 metadata-only unique append
   remains in the same roughly 0.34–0.36 s range as N=0/N=2,000.
2. **Exact retry had a real O(snapshot count) scan.** The batch→snapshot accelerator removes that scan
   for current indexed batches without making the accelerator authoritative.
3. **Full-data late-state append cost is a different effect.** The compaction profile measured about
   0.668 s after one bounded pass at N=10,000, where 5,268 active files still remained. That
   late-maintenance state is outside the normal target envelope and supports state-based maintenance
   before repeated provider-limit saturation.

The indexed recovery path described here does not introduce arbitrary retention or weaken
duplicate/evidence identity. Physical file maintenance remains a separate concern.

## Supported contract

The evidence supports the following contract:

- the live writer performs one append-or-recover operation instead of a separate preflight plus append;
- a current indexed exact retry has no all-snapshot provenance scan;
- deleting or corrupting the derived index does not change the durable commit and self-heals from
  DuckLake source provenance;
- restart and the existing local catalog lease contract remain valid;
- unique append in the N=10,000 metadata-only isolation remains comparable to N=0/N=2,000 rather than
  scaling with snapshot count;
- full-data file/query growth remains a separate physical-maintenance concern and is not hidden with retention.

This does not define a distributed/HA recovery index and does not make the sidecar required evidence.

## FILE duplicate lookup and row/file isolation (2026-10-06)

Local macOS 27.0.1 arm64, Python 3.14.7, DuckDB 1.5.5, base revision `dc32041`
with the working-tree scoped FILE lookup and `file_append_scaling.py`. Synthetic workload:
8 sources/assets, 35 channels, 2,000 observations per public batch, approximately 900 bytes of
repeated JSON metadata. Timings below are local medians, not performance guarantees.

The FILE duplicate lookup now groups events by source and file digest, filters their sample-index
range, then checks exact raw IDs. This relies on the producer contract that equal raw IDs imply
equal `(source_id, source_sha256, sample_index)`. Both built-in producers have identity tests;
external producers must honor the same contract. Range predicates allow unrelated files to be
pruned; wide or overlapping sample ranges and changed layouts can still increase scanned work.

The earlier public-append preparation measured five query repetitions at each checkpoint:

| Stored FILE rows | Active files | Recent append ms | Scoped duplicate ms | Former lookup ms | Latest ms | Page ms | Full-range aggregate ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 250,000 | 250 | 454.32 | 15.98 | 21.25 | 78.24 | 92.92 | 92.16 |
| 500,000 | 500 | 456.81 | 16.18 | 24.36 | 85.87 | 108.27 | 101.93 |
| 1,000,000 | 1,000 | 461.13 | 16.15 | 31.67 | 103.24 | 133.90 | 119.75 |
| 2,000,000 | 2,000 | 466.30 | 16.39 | 43.92 | 140.15 | 187.74 | 174.11 |

That run increased rows, small files, snapshots and the selected asset's time span together.
It establishes growth, but cannot attribute all query growth to row volume alone.

A revised default prepares rows with bulk SQL and uses the public path only for timed probes.
Five append probes add 10,000 rows beyond each requested checkpoint; actual counts are below.
This diagnostic mode creates fewer files/snapshots and bypasses recovery provenance during seeding.

| Actual rows | Active files | Append ms | Scoped duplicate ms | Former lookup ms | Latest ms | Page ms | Full aggregate ms | One-hour aggregate ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 10 | 439.77 | 15.77 | 17.41 | 72.33 | 72.90 | 77.64 | 76.22 |
| 260,000 | 29 | 449.44 | 16.24 | 20.43 | 76.20 | 81.49 | 82.51 | 82.11 |
| 510,000 | 48 | 451.06 | 16.00 | 22.02 | 78.14 | 89.12 | 83.94 | 83.33 |
| 1,010,000 | 67 | 453.18 | 16.16 | 26.58 | 80.31 | 93.71 | 89.57 | 86.29 |
| 2,010,000 | 86 | 458.12 | 16.49 | 34.99 | 82.35 | 96.06 | 91.09 | 81.86 |

Reports: `artifacts/file-scaling-review/seeded-n-scale/file-append-scaling.json` and
`artifacts/file-scaling-review/existing-2m-compaction.json` (generated local artifacts).
The small-file checkpoint results were preserved as
`artifacts/file-scaling-review/prior-public-append-scaling.json` from the preceding session;
its catalog was reused rather than rebuilt.

One bounded merge-only pass on the existing 2,000,000-row state (seven query repetitions):

| Metric | Before | After |
| --- | ---: | ---: |
| Raw / normalized rows | 2,000,000 / 2,000,000 | 2,000,000 / 2,000,000 |
| Ingestion batches | 1,000 | 1,000 |
| Active files | 2,000 | 1,552 |
| Physical files, including older snapshots | 2,000 | 2,064 |
| Scoped duplicate ms | 15.84 | 16.24 |
| Latest ms | 140.66 | 136.28 |
| Page ms | 181.35 | 174.11 |
| Full-range aggregate ms | 162.94 | 160.27 |
| One-hour aggregate ms | 115.18 | 107.37 |

The pass used 32 output operations per table, a 1 MiB target and inputs below 256 KiB.
After those same-row query measurements, eight additional public appends added 16,000 rows;
their median was 461.44 ms. They are a separate measurement, not part of the same-row comparison.
A pass on the bulk-prepared state reduced active files from 86 to 44 with little query change.
No snapshots were expired and no physical files were deleted.

These measurements support removing the global raw-ID scan: scoped lookup remains approximately
16 ms across the measured states while the former lookup grows. They also support treating small-file
layout separately from row volume. They do **not** establish constant cost up to 84.7M rows, identify
all remaining append costs, or prove that a single compaction pass solves query growth. Public-append
preparation also changes snapshot count, so the cross-layout comparison is suggestive rather than a
controlled isolation of file count alone. Explicit contended writer-lock timing remains outstanding;
existing lock contract tests cover exclusion/timeouts, not latency at scale.

Synthetic storage is highly compressible and must not replace the representative importer pilot's
243 B/observation sizing estimate (about 20.6 GB at 84,685,346 observations, before retained-snapshot
and maintenance overhead). Restart, exact retry, fingerprint equality, conflicting retry rejection
and duplicate rejection after merge-only compaction are validated on small states by contract tests.
