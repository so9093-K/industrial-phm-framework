# 0032. Score stored measurement history with operator-built models over fixed windows

Status: Accepted (2026-10-25)

Extends: [ADR-0025](0025-run-versioned-model-packages-over-ordered-asset-steps.md). Does not change
its package format, binding, one-transaction-per-step or fail-closed loading rules.

## Context

ADR-0025 runs packages over two step kinds: finalized live observation windows (ADR-0008) and
acquisition snapshots. A CSV registered through 운영 관리 becomes Asset History but produces neither,
and the only window feature set is the three-phase electrical one. A person can therefore see their
own data, its baseline departures and its forecast, but cannot apply an anomaly model to it. Package
creation is a developer CLI tied to the XJTU-SY and AI-Hub recipes.

## Decision

1. **History window step.** A third step kind, `history-window`, reads the bound source's stored
   observations of the package channels at a recorded DuckLake snapshot and groups them into fixed,
   epoch-aligned event-time windows. A window is a step only when it holds observations and the stream
   already has a later observation (so a live stream does not score a window that is still filling).
   The step key is the window start; the position is the window end in microseconds; the input
   reference records the snapshot, the window and a digest of the exact values used. Progress is
   judged by that same (source, point, channels) population at the same snapshot: a window is
   complete once that stream has a later observation (another source's newer data does not count),
   and each cycle starts at the stream's first observation after the cursor, so a gap of any length
   is passed over instead of being scanned.
2. **Feature set.** `history-window-stats-v1:<seconds>s` takes the mean, population standard
   deviation, minimum and maximum of each channel's good, non-conflicting values. A channel with fewer
   than three such values makes the step a recorded skip with that reason, as does a channel whose
   values in one window carry different units or meanings. Training rows and scored steps are
   produced by the same function.
3. **Operator-built package.** 이상 징후 › 모델 점수 lets a person choose one stored stream (source and
   measurement point, offering only that stream's signals and period), signals, a reference period
   and a window length, then explicitly build an Isolation Forest package
   (`operator-history-iforest-v1`) from that period's windows: robust scaling (median, IQR), the
   package format's deterministic refit, probe rows, and a threshold at the 99.5th percentile of the
   reference scores. At least 24 reference windows are required. The manifest records the asset,
   source, channels, period, snapshot, window count, a digest of the reference rows and each channel's
   unit and meaning, and states `operator-reference-not-validated`. A reference period in which a
   channel's unit or meaning changes builds nothing; a later window recorded with another unit or
   meaning is a skip with that reason. Building again with the same choices over the same reference
   values reuses that package and binding instead of adding an identical model; values changed inside
   the period (a later backfill) build a new package. The package is bound to that source and asset
   only; the runtime still never retrains on its own.
4. **Same downstream.** Results, score trend, intervals, monitor attention, AI explanation and review
   requests use the existing model paths; screens treat `history-window` as a time window.
   An example workspace refuses the build like any other new model or data (`example_records_only`).

## Consequences

- A person can score their own CSV or OPC UA history with a model trained on a period they chose, and
  the result says so. The reference period is a comparison choice, not verified normal operation.
- New observations of a live source are scored as their windows complete; a CSV scores once.
- Packages are immutable: a different period, signal set or window length is a new package and binding.
  Screens name such models by method and, when an asset has more than one, by the period and signal
  count each learned (`Isolation Forest (기준 10. 15. 00:00~10. 16. 06:36 · 신호 2개)`).
