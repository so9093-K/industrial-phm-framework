# Measurement history: meaning, presentation and scale

## Implemented boundary

`ChannelSemanticBinding` separates the source channel ID from an optional observed property, scope,
statistic and unit. AI-Hub raw labels do not establish these meanings. New imports use metadata v2;
legacy v1 JSON stays immutable and is displayed as a source label rather than a resolved property.
Exact legacy import recovery requires the explicit v1 serialization option. Changing interpretation
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
growing with the archive. Flush did not change import throughput, which remains about 630
observations/s (about 14 hours for 31 million records); the next scale step is profiling projection
and append cost, not storage format.

Not implemented: automatic periodic flush inside the live collection service (operators run
`flush-history`; it waits for the same catalog lease), small-file compaction for long live runs, and
catalog `VACUUM`. Dictionary normalization below remains useful for semantic updates and query
clarity, but needs its own measured benefit after flush before it is prioritized.

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

The next live-analysis milestone connects existing durable Window input to a versioned, reproducible
AnalysisRun and capability evidence, then explicit human Review Finding → Investigation → Maintenance
Review. COMPLETE channel coverage alone does not prove synchronized or analysis-ready input. Bind
input snapshot/window IDs, quality exclusions, algorithm/config version and observed scope before
producing evidence. Validated diagnostics, alarm rationalization, fleet risk, operational RUL and
maintenance recommendations remain separate capabilities requiring their own evidence.
