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
controlled isolation of file count alone. Contended writer-lock timing was measured later; see
the representative-size section below.

Synthetic storage is highly compressible and must not replace the representative importer pilot's
243 B/observation sizing estimate (about 20.6 GB at 84,685,346 observations, before retained-snapshot
and maintenance overhead). Restart, exact retry, fingerprint equality, conflicting retry rejection
and duplicate rejection after merge-only compaction are validated on small states by contract tests.

## Representative-size state and Monitor reads (2026-10-07, #316)

Local macOS 27.0.1 arm64, Python 3.14.7, DuckDB 1.5.5, base revision `dbb4514` with the
working-tree query change below. Synthetic SQL-prepared FILE rows, 35 channels at one-minute
cadence, 2,000-row public probe batches, approximately 900-byte metadata, medians of five
repetitions. These are local measurements, not capacity guarantees.

The representative workload is the air-compressor Training/raw archive (84,685,346 records,
72 devices; [reference profile](aihub-239-air-compressor-reference-profile.md)). The state is
prepared at that size directly; nothing is ingested over wall-clock time. Two axes are kept apart:

- **Unrelated N**: the queried asset is held at the representative member size (1,509,725 rows,
  `SourceData_16`) while 71 other devices grow total N to 84.7M.
- **Queried-asset N**: all rows belong to the queried asset, up to 24M rows (about 1.3 years of
  35 channels at one-minute cadence).

### Defect found and fixed

The Monitor runs `query_latest_asset_measurements` on every Refresh and
`query_multi_signal_measurement_aggregation` for its chart. Both joined raw metadata to the
selected rows by the hash `raw_evidence_id` alone, which cannot prune Parquet files, so every
raw row of every asset was scanned. The asset-latest read also ranked every stored row of the
asset in a window function. Both reads were therefore proportional to total N, and the
latest read additionally to the asset's whole history.

The change:

- raw metadata joins carry the static filters the joined rows already satisfy (asset, channel and
  time window for the chart; asset and latest-time floor for latest reads), as the single-channel
  page and aggregation reads already did;
- latest reads first compute a floor, the oldest per source/point/channel latest event time, with a
  grouped max over identity and time columns only. Every latest row is at or after it, so the
  ranking window, conflict detection and raw joins read only rows from the floor onward. A stale
  channel moves the floor back; the result is unchanged.

Identical results before and after on the 84.7M state (same digest of latest rows, conflict flags,
metadata and chart buckets), seven repetitions:

| Read on the 84.7M state | Before | After |
| --- | ---: | ---: |
| Monitor asset latest | 973.5 ms | 91.4 ms |
| Monitor six-signal 1h chart | 651.0 ms | 86.6 ms |
| Signals single-channel latest | 117.9 ms | 84.2 ms |

A contract test fixes the preserved behavior: a stale channel's latest value, a conflict at the
latest time, another asset's newer rows, FILE metadata, and empty results.

### Unrelated N, queried asset fixed at 1,509,725 rows (after the change)

| Stored rows | Active files | Append | Scoped duplicate | Former lookup | Monitor latest | Monitor 1h chart | Asset discovery | Full-range aggregate | Fixed 1h aggregate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,539,725 | 32 | 451.3 | 16.98 | 31.87 | 83.1 | 90.4 | 47.0 | 108.0 | 80.4 |
| 10,030,000 | 134 | 460.6 | 16.45 | 88.82 | 81.9 | 79.9 | 52.5 | 115.6 | 80.9 |
| 40,030,000 | 239 | 463.7 | 16.13 | 286.70 | 88.5 | 83.0 | 74.5 | 113.6 | 83.9 |
| 84,715,346 | 345 | 453.7 | 16.22 | 580.68 | 87.1 | 88.1 | 97.7 | 121.3 | 86.5 |

Milliseconds. Bare connect/attach is about 40 ms of every read. The 84.7M state holds 11.1 GB of
active synthetic Parquet.

### Queried-asset N (after the change)

| Asset rows | Append | Scoped duplicate | Monitor latest | Single-channel latest | Monitor 1h chart | Full-range page | Full-range aggregate | Fixed 1h aggregate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 280,000 | 453.2 | 16.41 | 82.8 | 79.0 | 80.2 | 102.3 | 89.7 | 79.6 |
| 1,539,725 | 449.3 | 16.08 | 83.4 | 80.8 | 77.6 | 116.8 | 118.3 | 76.6 |
| 6,030,000 | 447.2 | 16.16 | 89.0 | 85.4 | 75.4 | 159.6 | 234.6 | 84.6 |
| 24,030,000 | 448.1 | 16.01 | 126.2 | 110.8 | 77.1 | 311.9 | 718.4 | 82.0 |

### Catalog lock

Every read and write holds the same local catalog lock, so a read's hold time bounds how long a
collector append waits behind it. The append connect was measured while a Monitor asset-latest
read held the lock in another thread:

| State | Monitor read hold | Append hold | Append connect, uncontended | Append connect behind Monitor read |
| --- | ---: | ---: | ---: | ---: |
| 84.7M total, asset 1.5M | 67.0 ms | 431.4 ms | 24.8 ms | 79.9 ms |
| asset 24M | 103.8 ms | 416.0 ms | 24.7 ms | 135.7 ms |

The waits include the lock's 50 ms polling interval. The reverse wait, a Monitor read behind an
append, is bounded by the append hold of about 0.42–0.43 s, which does not grow with N.

### Judgment

| Operation | Cost versus N |
| --- | --- |
| FILE append, scoped duplicate check | constant in total and asset N |
| Monitor 1h chart, fixed-window aggregate | constant in total and asset N |
| Monitor asset latest, single-channel latest | constant in unrelated N; proportional to the asset's own history with a narrow-scan slope of about 1.3–1.8 ms per million asset rows (exploratory runs of the previous query: about 0.35 ms per **thousand** asset rows) |
| Asset discovery (each Operations snapshot) | proportional to total N, about 0.6 ms per million rows; 98 ms at 84.7M |
| Full-range page and aggregate | proportional to rows in the requested range, by design; Monitor and Signals request bounded ranges |
| Catalog lock wait behind a Monitor read | follows the Monitor read: about 80 ms at the representative size |

At the representative size every Monitor read stays below 100 ms and an append waits about 80 ms
behind one. Nothing measured requires a storage migration or retention policy. Asset discovery
and latest reads remain linear with small slopes; a derived latest/asset index would be justified
only by a state size well beyond these points (asset discovery reaches about 0.5 s near 10× the
archive) and is not added.

### Limitations

- The SQL-prepared state has few large files. The v5 importer writes one file per batch (about
  1,586 files per 1.5M rows, about 89k files for the archive without compaction). File-count
  growth is a physical-maintenance concern measured earlier in this note and in the
  [compaction evidence](history-compaction-evidence.md); this run does not repeat it at 89k files.
- Synthetic rows compress far better than real data. Storage sizing remains the importer pilot's
  243 B/observation (about 20.6 GB at 84.7M observations).
- One host, one process at a time; lock contention is local single-host serialization, not a
  distributed or multi-writer measurement.

Reports: `artifacts/316-n-scale/unrelated-assets/file-append-scaling.json`,
`artifacts/316-n-scale/queried-asset/file-append-scaling.json` and
`artifacts/316-n-scale/compare-84m.jsonl` (generated local artifacts).
