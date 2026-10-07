# History maintenance tools

## Non-destructive compaction benchmark

`compaction_benchmark.py` is the repeatable non-destructive compaction scale experiment. It creates an isolated
DuckLake catalog, preloads a known number of commits, records storage/query/append metrics, runs
**merge-only** compaction, and then verifies old snapshot fingerprints plus exact batch recovery.

Run separate empty roots for each accumulated-state size:

The default workload writes 35 observations per commit across 35 channels, matching the live three-phase replay
channel-count profile while keeping N focused on accumulated commits/files rather than row volume.

```bash
uv run --locked --extra history python -m tools.history.compaction_benchmark \
  --root artifacts/compaction-n0 \
  --commits 0 \
  --max-compacted-files 32 \
  --target-file-size-bytes 1048576 \
  --max-file-size-bytes 262144

uv run --locked --extra history python -m tools.history.compaction_benchmark \
  --root artifacts/compaction-n2000 \
  --commits 2000 \
  --max-compacted-files 32 \
  --target-file-size-bytes 1048576 \
  --max-file-size-bytes 262144

uv run --locked --extra history python -m tools.history.compaction_benchmark \
  --root artifacts/compaction-n10000 \
  --commits 10000 \
  --max-compacted-files 32 \
  --target-file-size-bytes 1048576 \
  --max-file-size-bytes 262144
```

The numeric file-size/work bounds above are experiment inputs, not retention policy. The first
profile is a tier-0 layout: files below 256 KiB are merged toward 1 MiB outputs. DuckLake persists
`target_file_size`, so the selected target becomes a physical-layout setting for later writes and
compactions. Compare `compaction-benchmark.json` across runs before choosing an operational profile.

The report records:

- Git/Python/OS/DuckDB/DuckLake environment fingerprint
- snapshot, active file, scheduled-for-deletion and physical Parquet populations
- append/query time and Python peak allocation before/after compaction
- compaction duration and files processed/created
- canonical SHA-256 for representative old snapshots
- exact batch-recovery preservation
- explicit zero counts for snapshot expiration, cleanup, CHECKPOINT and VACUUM

This benchmark does not delete physical files. A post-compaction increase in files scheduled for
deletion is expected: replaced files remain on disk until a separately specified retention and cleanup policy.


## Latest measured result

The measured compaction evidence is recorded in
[`docs/research/history-compaction-evidence.md`](../../docs/research/history-compaction-evidence.md).

N=10,000 is a late-maintenance stress point, not a production pass threshold. One bounded pass
processed 14,799 of 20,003 active files and stopped at the provider output-operation limit, leaving
5,268 active files for a later pass. This is expected; normal maintenance should occur before repeated
provider-limit saturation. The benchmark also showed that compaction recovers file/query cost but does
not remove the separate accumulated-history append cost measured by the append profile.


## Live append scaling profile

`append_profile.py` is the repeatable live-history append scaling diagnostic. It breaks one OPC UA history append/retry into
connect/attach, initialization, batch identity, raw duplicate lookup, insert/commit, and snapshot
provenance stages.

For a small full-data state:

```bash
uv run --locked --extra history python -m tools.history.append_profile \
  --root artifacts/append-profile-n2000 \
  --commits 2000
```

To isolate snapshot/catalog growth without creating the full raw/history file population:

```bash
uv run --locked --extra history python -m tools.history.append_profile \
  --root artifacts/append-profile-metadata-n10000 \
  --commits 10000 \
  --metadata-only
```

The measured results and interpretation are recorded in
[`docs/research/history-append-scaling-evidence.md`](../../docs/research/history-append-scaling-evidence.md).
Metadata-only is a diagnostic isolation mode, not an operational ingestion path.

## FILE backfill cost versus stored rows

`file_append_scaling.py` measures append, duplicate lookup, latest/page/aggregate queries,
a fixed one-hour aggregate window, and storage at explicit stored-row checkpoints. The default
uses bulk SQL to prepare row volume, then times repeated public `append_file_batch()` calls.
Seeded rows are diagnostic state; their ingestion batches have no recovery fingerprint and
must never be used as importer/recovery evidence. Use a dedicated empty root.

```bash
uv run --locked --extra history python -m tools.history.file_append_scaling \
  --root artifacts/file-append-scaling \
  --checkpoints 0,250000,500000,1000000,2000000 \
  --compact-at-end
```

Use `--prepare-via-append` in a separate root to prepare many small files and snapshots through
public appends. It is a file-layout comparison and costs more than bulk preparation. Compare
both modes to distinguish row volume from file/snapshot growth; changing all of them together
cannot establish which variable causes an increase.

Reports include actual `stored_rows`: public probes add `repeats × batch_size` rows after each
SQL-prepared checkpoint. Active Parquet counts/bytes are separate from physical files retained
for older snapshots. `--compact-at-end` performs one bounded merge-only pass (32 output operations
per table, files below 256 KiB toward 1 MiB), then measures queries at the identical row count.
Append probes after compaction are reported separately with their before/after row counts.
Compaction changes the persistent target-file-size option in this isolated catalog.

The fixed-window aggregate holds the queried time span constant; the full-range aggregate grows
with the selected asset's data.

Each checkpoint also measures the Monitor reads (asset latest, a six-signal one-hour chart and
asset discovery), bare connect/attach cost, and the catalog lock: how long one Monitor read and
one append hold it, and how long an append's connect takes while a Monitor read holds it. Those
contention appends are counted in `stored_rows` before the row count is recorded.

Two axes separate the stored-row variables. Total N with the queried asset held fixed at the
representative member size (72 devices, as in the air-compressor Training/raw archive):

```bash
uv run --locked --extra history python -m tools.history.file_append_scaling \
  --root artifacts/316-n-scale/unrelated-assets \
  --sources 72 --queried-asset-rows 1509725 \
  --checkpoints 1509725,10000000,40000000,84685346
```

The queried asset's own history (all rows in one asset):

```bash
uv run --locked --extra history python -m tools.history.file_append_scaling \
  --root artifacts/316-n-scale/queried-asset \
  --sources 1 --checkpoints 250000,1509725,6000000,24000000
```

The 84.7M-row state uses about 10 GB of synthetic Parquet and takes about two minutes to prepare. Results and limitations are recorded in
[`history-append-scaling-evidence.md`](../../docs/research/history-append-scaling-evidence.md).
Do not replace these state comparisons with full-archive or long wall-clock runs. Estimate storage
using measured bytes per observation × N; synthetic compression is not a production sizing estimate.

## Live retention cost versus snapshot count

`retention_profile.py` prepares N live commits (`--rows-per-commit` rows each, every
`--old-every`-th one older than the cutoff), then measures one `apply_live_retention()` run:
the dry run, every catalog lease hold, snapshots expired, files removed, catalog bytes and
catalog-inlined rows, and a public append before and after. The cutoff is taken after the last
prepared commit, so the run expires a backlog of all N snapshots at once. Prepared rows are copied
from one public batch with the same commit metadata shape; they are diagnostic state.

```bash
uv run --locked --extra history python -m tools.history.retention_profile \
  --root artifacts/retention-profile/n20000 --commits 20000

uv run --locked --extra history python -m tools.history.retention_profile \
  --root artifacts/retention-profile/r90-n8000 --commits 8000 --rows-per-commit 90 --old-every 10
```

Preparation slows as snapshots accumulate (about 13 ms per commit up to 1,000 and 42 ms on average
up to 50,000), so 50,000 commits take about 35 minutes. Results are recorded in
[`history-retention-evidence.md`](../../docs/research/history-retention-evidence.md).
