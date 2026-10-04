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
