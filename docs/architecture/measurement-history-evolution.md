# Measurement history: meaning, presentation and scale

## Implemented boundary

`ChannelSemanticBinding` separates the source channel ID from an optional observed property, scope,
statistic and unit. AI-Hub raw labels do not establish these meanings. New imports use metadata v4,
which applies `aihub-239-semantics-v2` only to items where the provider unit table and a full-archive
relation profile agree (frequency, phase/line voltage averages, phase currents), with member
exceptions where a relation fails; every other item stays unresolved. v3 (`semantics-v1`),
v2 (all unresolved) and legacy v1 JSON stay immutable; v1 is displayed as a source label rather than
a resolved property. Exact recovery of an earlier import requires its explicit serialization option. Changing interpretation
never overwrites historical batch fingerprints or creates another copy of the same raw observation.

`HistoricalMeasurement.source_quality` separates FILE unknown source quality from numeric availability.
Its existing persisted `status_good` field remains a compatibility field: FILE numeric availability,
OPC UA protocol Good. Future consumers must use source_quality for quality meaning. Conflict detection
is separate from both quality and availability. No field asserts asset condition.

Latest stored event age is independent of receipt-based `SourceFreshnessPolicy`. Historical backfill,
import and replay do not acquire a stale-live-source classification. LIVE history rows refer the user
to the existing Sources policy/receipt surface; history age is not reused as a live receipt.

15-minute/custom views return bounded raw points and show requested versus returned ranges/counts.
A custom range whose raw points exceed the budget switches to 200 full-interval buckets, because
historical assets are outside every relative preset. Displayed event times are UTC, matching the chart.
24-hour/7-day views query the full interval into 200/100 temporal buckets, separating source,
measurement point and serialized binding/semantic interpretation. A response over 2,000 groups fails
explicitly rather than dropping a subset. Counts include nulls, conflicting values and protocol
non-good values; these are excluded from min/max/mean. Exclusion counts can overlap. Equal-value
repeats remain observations, so mean is observation-weighted and not a time-weighted mean, source
statistic or energy estimate. Empty intervals are not interpolated. Red time markers signal excluded
observations, not zero. Snapshot ID, bucket bounds and interpretation are returned for inspection;
individual raw provenance can be inspected using the custom range view.

A bounded response does not bound the underlying scan time. Long aggregate queries hold the local
catalog lease and can delay a writer; there is no measured full-archive latency/throughput guarantee.
The lock coordinates cooperating local processes; it is not a distributed read/write service.

## OPC UA semantic snapshots in raw evidence

An OPC UA DataChange carries the source's registered `ChannelSemanticBinding` snapshot. It is stored with
the raw delivery as canonical JSON (`raw.opcua_data_change.semantic_binding_json`) and restored by
`query_opcua_events`/`get_opcua_event`, so windows rebuilt from history keep the same semantics as the
spool path. `query_channel_observations` reads FILE metadata semantics and OPC UA snapshots into one
shape for analysis eligibility, and accepts a binding only when its `source_id`/`channel_id` name the
raw row it is stored with; any other snapshot reads as unresolved.

OPC UA batch fingerprints are versioned. New commits record `fingerprint_version = opcua-semantic-v2`
and fingerprint the semantic snapshot. A commit without a version was written before this change,
including spool batches that already carried a snapshot but were fingerprinted without it; recovery
verifies those with the legacy semantics-free fingerprint. So a batch committed by the earlier writer
and not acknowledged before a crash still recovers after upgrade, and its raw rows stay without a
semantic snapshot instead of being backfilled with the current binding.

Catalogs created before this column gain it once as a nullable column; earlier rows stay without
semantics (unresolved), never reinterpreted. Time travel to a snapshot recorded before the column
existed reads OPC UA semantics as unresolved instead of failing, so earlier analysis results remain
recomputable at their recorded snapshot.

## Measured storage baseline (2026-09-29)

One real extruder member (`7.압출기/SourceData_127.json`, device 2223, 48 source-local hours, 35
channels) was imported with metadata v2 into an empty local catalog. This is one member on one
developer machine (DuckDB 1.5.5, DuckLake format 1.0), not a capacity guarantee.

| Measure | Value |
| --- | --- |
| Observations / batches | 100,800 / 51 (batch size 2,000) |
| Import wall time | 161 s (about 630 observations/s) |
| `source_metadata_json` | about 1,039 B per row; repeated binding/semantics about 75% |
| Catalog after import | 240 MB SQLite, 0 B Parquet (all rows inlined into the catalog) |
| After `ducklake_flush_inlined_data` | 21 MB Parquet (15 MB raw, 6.8 MB history) + 188 KB catalog |
| Channels / latest / 2,000 raw / 200-bucket aggregate | 0.08 / 0.11 / 0.52 / 0.61 s after flush; 0.09 / 0.18 / 0.63 / 0.72 s inlined |

The dominant cost is DuckLake data inlining, not JSON repetition: every append stays as SQLite rows,
about 2.4 KB per observation. Linear extrapolation to roughly 31 million records is about 74 GB of
catalog; that is not acceptable. Parquet dictionary compression reduced the same repeated JSON
about 11×.

## Implemented inlined-data flush

`DuckLakeAssetHistory.flush_inlined_data()` moves inlined rows to Parquet under the shared catalog
lease. It creates one storage snapshot and changes no logical rows: earlier snapshots return the same
rows through time travel, and batch recovery still resolves each batch's original commit snapshot.
A flush with nothing inlined creates no snapshot. The AI-Hub import tool flushes after every 10 newly
appended batches (`--flush-every-batches`) and at the end; exact retries of recovered batches do not
flush. `industrial-phm operations flush-history` flushes an existing catalog, including FILE
backfills and live collection history.

Same member and range, measured again with flush during import:

| Flush interval | Import | SQLite catalog file | Parquet | Files | 2,000 raw / 200-bucket aggregate |
| --- | --- | --- | --- | --- | --- |
| none | 161 s | 240 MB | 0 B | 0 | 0.63 / 0.72 s |
| every 50 batches | 163 s | 224 MB | 21 MB | 6 | 0.53 / 0.64 s |
| every 10 batches | 164 s | 45 MB | 21 MB | 18 | 0.24 / 0.23 s |

SQLite reuses the freed pages (99.9% of the 50-batch catalog was free pages) and does not shrink the
file. The catalog is therefore bounded by roughly one flush interval of inlined rows instead of
growing with the archive. Flush did not change import throughput (about 630 observations/s).

## Import and query throughput

Profiling the same import showed 60% of wall time in failed `import pandas` attempts: DuckDB probes
pandas for every bound Python value, and without pandas each probe rescans `sys.path`. The adapter
now binds one typed list per column (`INSERT ... SELECT unnest(?::T[])`) and, only while pandas is not
importable, caches the absent module for the duration of that bind. Stored rows are identical to the
previous per-row `executemany` (`EXCEPT ALL` difference 0 in both directions for raw, history and
batch tables; identical batch fingerprints). Column inserts write Parquet directly, so imports no
longer depend on flush; flush remains for small live batches.

The acquisition and history path does not use pandas or any DataFrame library, and neither is a
project dependency. `_cache_absent_pandas_import()` only avoids DuckDB's per-value pandas probe; the
path is domain events → typed Python values → typed column lists → DuckDB `UNNEST` → DuckLake. A
DataFrame library is not added to the collector. Arrow/Polars are considered only for large offline
transformation, feature engineering or research over Asset History, and only when that is a measured
bottleneck, hard to express in DuckDB SQL, and faster and simpler in a benchmark (Python list binding
vs Arrow vs Polars/Arrow). If Arrow binding wins, it replaces the pandas-probe workaround.

The page, aggregate and latest queries outer-joined the whole raw FILE table to attach provenance,
which built a hash table over every raw row and its JSON. They now filter raw rows by the same
asset, channel and time range first (FILE raw and history rows come from one event and share them).
Results are unchanged; aggregate means can differ in the last binary digit between any two runs,
including before this change, because parallel summation order varies.

| Extruder member `SourceData_127.json` | Before | After |
| --- | --- | --- |
| 48 h import (100,800 observations) | 161 s | 36 s |
| Whole member (1,209,600 observations, 605 batches) | not run | 350 s, about 3,460/s |
| Append per 2,000-row batch, first → last 10% | — | 0.458 → 0.483 s |
| 2,000 raw points / 200-bucket aggregate, 48 h, 1.2 M rows stored | 1.31 / 1.28 s | 0.10 / 0.09 s |
| Aggregate over the whole member | 14.9 s | 0.59 s |

Whole member storage: 259 MB Parquet (about 214 B per observation, raw JSON included), 1,271 files,
3 MB catalog. Merging adjacent files did not change query time. Append time grows slowly because
each batch's duplicate check scans existing raw evidence IDs; linear extrapolation to about 31
million records is roughly 1.1 s per batch at the end and 3.5–4.5 hours in total on this machine.
That estimate is not a measured full-archive run.

## Non-destructive small-file compaction

#317-A treats physical file compaction as a DuckLake-specific maintenance capability, not as an
application or acquisition responsibility. `DuckLakeAssetHistory.compact_adjacent_files()` uses the same local catalog lease as readers/writers
for each table and calls only DuckLake merge-adjacent-files. Tables are compacted in separate provider
calls/connections so the lease and native-memory working set are released between tables; the overall
operation is intentionally not cross-table atomic and is safely retryable. The operation requires
DuckLake's per-table output-operation limit, an explicit persistent
`target_file_size` physical-layout setting, and may restrict eligible source-file sizes. The provider
operation limit does not cap how many input files can feed one output, so RSS/HWM and lock-hold bounds
remain measured acceptance criteria rather than inferred guarantees. The initial tier-0 validation
merges files below 256 KiB toward 1 MiB outputs rather than the DuckLake default 512 MiB target.

Compaction is intentionally separate from retention. Existing snapshot IDs remain part of the
acceptance contract: representative raw/history rows are canonically fingerprinted before compaction
and the same snapshots must produce the same fingerprint afterwards. Existing batch exact-retry
provenance must also resolve to its original commit. Old physical Parquet files replaced by a merge can
remain scheduled for later deletion; #317-A measures active files separately from scheduled and physical
files.

Terminology is fixed across code and operations:

- **flush**: catalog-inline rows → Parquet
- **compact**: active small Parquet files → fewer/larger active Parquet files
- **expire**: remove historical snapshot visibility
- **cleanup**: delete physical files no longer required by DuckLake
- **vacuum**: reclaim metadata-catalog storage

#317-A does not call snapshot expiration, old/orphan-file cleanup, CHECKPOINT or VACUUM and does not
run maintenance from the collector hot path. Retention/deletion and automatic scheduling remain
#317-B after representative archive measurements.

Dictionary normalization below remains useful for semantic updates and query clarity, but needs its
own measured benefit after compaction before it is prioritized.

## Metadata normalization before full-archive ingestion

The current slice stores raw record and repeated binding/semantic JSON in each observation. This is
acceptable for the exercised slice, not an approved storage plan for roughly 31 million records.
No full-archive import is introduced by these changes. The next storage migration should:

1. Create immutable source-binding and semantic-binding tables. IDs are hashes of a versioned,
   canonical JSON encoding; store the encoding version and exact canonical payload. The source
   binding includes source/asset/device IDs, timezone and evidence. Semantic binding includes source,
   channel, observed property/scope/statistic/unit and evidence/version. Never update rows in place.
2. Store binding_id and semantic_binding_id with observation-specific archive/member/index/raw-time
   evidence. Keep raw-record provenance or a durable verified archive reference. Do not delete raw
   bytes merely because a dictionary join can reconstruct some fields.
3. Insert dictionaries, observations and batch checkpoint atomically. Read legacy JSON and normalized
   rows through one projection. Verify existing raw IDs, retry fingerprints, history counts, nulls,
   conflicts and interpretation equality before any cutover. Do not rewrite old evidence in place.
4. Benchmark both archives on representative members: catalog/data bytes per observation, import
   throughput, latest/raw/aggregate query latency and writer lock wait. Include failure/restart and
   exact-retry recovery. Publish measurements and acceptance targets before enabling full ingestion.

This is the migration design, not an implemented normalization or a claim of measured capacity.
A table-layout change is kept out of the current meaning correction because it requires its own
legacy-catalog migration/recovery evidence.

## Product sequence and gates

Asset Detail is the primary evidence journey: identity → current observations/history → analysis
→ findings → review. Operations cells own widgets/layout/wiring; interpretation and aggregation remain
in application/presentation/history modules. No generic UI framework is required.

Power Quality / Energy Measurement capability requires evidenced physical measurement points,
properties, units/scaling, source timezone, cadence and aggregation semantics. A raw label or a
configured Asia/Seoul assumption is not that evidence. Select one documented measurement and define
its analysis eligibility, exclusions, expected outputs and verification fixture before adding an
analysis action. Do not integrate power into energy across unknown gaps/cadence or manufacture
power-quality metrics from unspecified source averages.

Any live-analysis path must connect durable Window input to versioned, reproducible AnalysisRun and
capability evidence without treating COMPLETE channel coverage as synchronized or analysis-ready input.
Bind input snapshot/window IDs, quality exclusions, algorithm/config version and observed scope before
producing evidence. Diagnostics, alarm rationalization, fleet risk, operational RUL and maintenance
recommendations remain separate capabilities requiring their own evidence.
