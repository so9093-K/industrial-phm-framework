# Phase 10 DuckLake non-destructive compaction evidence

Date: 2026-10-01  
Scope: #317-A / PR #343  
Runtime: CPython 3.14.7, DuckDB v1.5.5, DuckLake d8a1881e, Linux x86_64  
PR head used for the final benchmark: `55758882a95f70f23a5f5cfa40f50805ed320f2a`
(the Actions checkout itself is a synthetic pull-request merge commit).

## Question

Can the live Asset History reduce accumulated small Parquet files without expiring snapshots,
deleting files, weakening evidence identity, or coupling maintenance to the collector hot path?

The answer is **yes for non-destructive file/query maintenance**, with an explicit late-maintenance
boundary. This experiment does **not** show that live append cost is independent of accumulated
history; that remaining issue is tracked separately in #344.

## Workload

Each commit contains 35 OPC UA observations across 35 channels. State is prepared at N=0, N=2,000
and N=10,000 commits. The benchmark then:

1. records storage and process memory,
2. fingerprints representative historical snapshots,
3. measures latest/page/aggregate queries,
4. appends one new probe batch,
5. compacts each DuckLake table in a separate provider call/connection,
6. rechecks old snapshot fingerprints and exact batch recovery,
7. appends another new batch and repeats query/storage measurements.

Compaction profile:

- eligible source files: < 256 KiB
- target file size: 1 MiB
- `max_compacted_files=32` per table
- no snapshot expiration
- no old/orphan-file cleanup
- no CHECKPOINT
- no VACUUM

`max_compacted_files` is DuckLake's output-compaction-operation limit, **not** an input-file
count limit.

The benchmark preloader reuses one already initialized/leased connection so state preparation is
deterministic and avoids connection setup dominating 10,000 iterations. Its `preload_seconds` is
therefore not an operational ingestion-throughput measurement.

## Results

| Metric | N=0 | N=2,000 | N=10,000 |
| --- | ---: | ---: | ---: |
| active files at N | 0 | 4,001 | 20,001 |
| active files immediately before compaction | 2 | 4,003 | 20,003 |
| active files after one compaction pass | 2 | 21 | 5,268 |
| files processed | 0 | 4,002 | 14,799 |
| output files created | 0 | 20 | 64 |
| provider compaction duration | 0.94 s | 2.78 s | 7.12 s |
| measured compaction call total | 1.44 s | 3.51 s | 8.88 s |
| append before compaction | 0.554 s | 0.377 s | 0.684 s |
| append after compaction | 0.345 s | 0.356 s | 0.668 s |
| aggregate query before | n/a | 1.277 s | 5.425 s |
| aggregate query after | 0.343 s | 0.354 s | 1.677 s |
| RSS at N | 190 MB | 195 MB | 207 MB |
| RSS immediately before compaction | 192 MB | 243 MB | 318 MB |
| RSS immediately after compaction | 194 MB | 264 MB | 304 MB |
| process HWM immediately before compaction | — | 0.83 GB | 3.10 GB |
| process HWM after compaction | 0.27 GB | 1.97 GB | 3.67 GB |
| old snapshot fingerprints preserved | yes | yes | yes |
| existing batch exact retry preserved | yes | yes | yes |
| destructive operations | 0 | 0 | 0 |

At N=2,000 one pass reduced active files by about 99.5% and aggregate query time by about 72%.
The table-separated implementation also reduced the earlier whole-catalog N=2,000 process HWM
from about 3.21 GB to 1.97 GB. The HWM moved from about 0.83 GB before compaction to 1.97 GB after
it, while current RSS returned to about 264 MB; this is a transient native working set rather than
persistent RSS retention.

At N=10,000 one bounded pass reduced active files by about 73.7% and aggregate query time by about
69%. Current RSS did not increase across compaction (about 318 MB → 304 MB). Lifetime HWM was
already about 3.10 GB after the large historical fingerprint/query oracle and rose to about 3.67 GB
after compaction, so the compaction stage added about 0.53 GiB to the observed process high-watermark.

## Late-maintenance boundary

N=10,000 is intentionally a stress observation, not a normal-operation pass threshold.

At N=2,000, the compaction result used 13 raw-table output operations and 7 measurement-table output
operations, below the provider limit of 32, and drained almost all eligible active files.

At N=10,000, both populated tables reached the 32-output-operation limit (64 outputs total). One pass
therefore processed 14,799 input files but deliberately left 5,268 active files. This is the expected
bounded-provider behavior: a late backlog can require repeated passes.

The maintenance trigger candidate is therefore **state based**, not time based:

- eligible small-file population and size distribution,
- provider output-operation saturation,
- query/commit latency and available maintenance envelope.

No universal numeric auto-trigger is approved here. The operational direction is to compact before a
single pass repeatedly saturates the provider output limit, while keeping the command explicit until
representative field/archive measurements justify automation.

## Evidence and failure semantics

The experiment verifies that merge-only compaction:

- leaves representative pre-existing snapshot IDs queryable,
- produces identical canonical SHA-256 for raw/history/batch evidence at those snapshots,
- preserves exact batch retry and its original commit provenance,
- permits a subsequent new history write,
- uses the same local catalog lease as normal history access,
- releases that lease between table-level provider calls,
- schedules replaced physical files for later deletion but does not delete them.

The overall multi-table maintenance operation is intentionally not cross-table atomic. Each completed
DuckLake table compaction is a valid snapshot; retrying the command continues from the valid current
state.

## Important non-result: append scaling remains

Small-file compaction is not the complete explanation for live history append cost:

- N=2,000: 0.377 s → 0.356 s after compaction
- N=10,000: 0.684 s → 0.668 s after compaction

The N=10,000 preloader also took 2,984 s versus 293 s at N=2,000. The preloader is not an operational
throughput benchmark, but together with the one-batch probe it shows that an accumulated-history
dependency remains.

The append path separately performs catalog attach/initialization, batch identity lookup, raw-evidence
duplicate rejection, insert/commit and committed-snapshot provenance lookup. #344 owns the next
isolation step and must preserve exact retry/conflict/duplicate semantics. #321 therefore remains open
after #317-A; #343 closes only the small-file/query maintenance portion of the Phase 10 storage gate.

## 317-A conclusion

**PASS for non-destructive compaction semantics and file/query recovery.**

Supported by this result:

- explicit merge-only maintenance,
- evidence-preserving historical snapshots,
- active/scheduled/physical file distinction,
- table-separated lease/retry boundary,
- measured N=2,000 and late-maintenance N=10,000 resource envelopes,
- no destructive lifecycle operation.

Not claimed by this result:

- automatic scheduling,
- retention/expiration/physical cleanup policy,
- production-wide memory SLO,
- N-independent live append cost,
- distributed/HA maintenance.

Retention/deletion remains #317-B after KAIST/#316 evidence. Live append scaling remains the Phase 10
blocker in #344.
