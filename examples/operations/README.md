# Operations bundled demo

This directory contains a small synthetic CSV snapshot used only to exercise the
Operations product workflow without downloading an external dataset.

The signal is deterministic synthetic example data. It does **not** represent a real
bearing condition, fault, anomaly, degradation trajectory or remaining useful life.

From `apps/operations.py`, use **Prepare bundled demo source** on the Overview screen.
The action registers this snapshot through the normal FILE-source validation path. Then:

1. Open **Sources** and select `demo-bearing-snapshot`.
2. Run **Analyze FILE snapshot**.
3. Open **Investigation** and inspect the persisted AnalysisRun + feature evidence.
4. Create the explicit **REVIEW_REQUIRED** finding.
5. Open **Maintenance** and add a note, acknowledge, then close the human review.

The workflow demonstrates product interaction and persistence only. It is not a model
performance or predictive-maintenance validation demo.
