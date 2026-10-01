# History maintenance tools

## Non-destructive compaction benchmark

`compaction_benchmark.py` is the repeatable #317-A scale experiment. It creates an isolated
DuckLake catalog, preloads a known number of commits, records storage/query/append metrics, runs
**merge-only** compaction, and then verifies old snapshot fingerprints plus exact batch recovery.

Run separate empty roots for each accumulated-state size:

```bash
uv run --locked --extra history python -m tools.history.compaction_benchmark \
  --root artifacts/compaction-n0 \
  --commits 0 \
  --max-compacted-files 32 \
  --max-file-size-bytes 1048576

uv run --locked --extra history python -m tools.history.compaction_benchmark \
  --root artifacts/compaction-n2000 \
  --commits 2000 \
  --max-compacted-files 32 \
  --max-file-size-bytes 1048576

uv run --locked --extra history python -m tools.history.compaction_benchmark \
  --root artifacts/compaction-n10000 \
  --commits 10000 \
  --max-compacted-files 32 \
  --max-file-size-bytes 1048576
```

The numeric file-size/work bounds above are experiment inputs, not production policy. Compare
`compaction-benchmark.json` across runs before choosing any operational threshold.

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
