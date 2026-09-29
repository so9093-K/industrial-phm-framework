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
