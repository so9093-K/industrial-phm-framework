# History maintenance tools

## Non-destructive compaction benchmark

`compaction_benchmark.py` is the repeatable #317-A scale experiment. It creates an isolated
DuckLake catalog, preloads a known number of commits, records storage/query/append metrics, runs
**merge-only** compaction, and then verifies old snapshot fingerprints plus exact batch recovery.

Run separate empty roots for each accumulated-state size:

The default workload writes 35 observations per commit across 35 channels, matching the Phase 10
channel-count sanity profile while keeping N focused on accumulated commits/files rather than row volume.

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
deletion is expected: replaced files remain on disk until a future, separately specified retention
and cleanup policy (#317-B).


## Latest measured result

The final #317-A measurements are recorded in
[`docs/research/phase10-history-compaction.md`](../../docs/research/phase10-history-compaction.md).

N=10,000 is a late-maintenance stress point, not a production pass threshold. One bounded pass
processed 14,799 of 20,003 active files and stopped at the provider output-operation limit, leaving
5,268 active files for a later pass. This is expected; normal maintenance should occur before repeated
provider-limit saturation. The benchmark also showed that compaction recovers file/query cost but does
not remove the separate accumulated-history append cost tracked in #344.
