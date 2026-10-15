"""Judge XJTU-SY operational anomaly inference against the acceptance protocol v1 (§1, §2.2).

Replays every fold-1 bearing not used for fitting through the real snapshot store, PHM runner
and store, then compares the operational step outputs with the stored research evidence and
with a batch evaluation of the same package. Writes one JSON verdict; exits non-zero on FAIL.

    uv run --no-sync python -m tools.phm.verify_xjtu_operational <workspace> \\
        --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets --output <verdict.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_runner import PackageCache, run_snapshot_bindings
from industrial_phm.demo.xjtu_snapshot_replay import replay_xjtu_bearing
from industrial_phm.experiments.xjtu_evaluation import late_vs_middle_rank_probability, spearman_rho
from industrial_phm.experiments.xjtu_lifecycle import LATE_THIRD, MIDDLE_THIRD, lifecycle_segment
from industrial_phm.models.package import ModelTask, is_retired_package, load_model_package
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

VALIDATION = ("Bearing1_2", "Bearing2_2", "Bearing3_2")
HOLDOUT = ("Bearing1_1", "Bearing2_1", "Bearing3_1")
RHO_TOLERANCE = 1e-9
SEQUENTIAL_BATCH_TOLERANCE = 0.0
_RESULTS = Path("docs/research/results")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, default=_RESULTS)
    args = parser.parse_args(argv)

    workspace = OperationsWorkspace(args.workspace.resolve())
    packages = {
        load_model_package(path).manifest.output.task: path.name
        for path in sorted(workspace.models_path.iterdir())
        if (path / "package.json").is_file() and not is_retired_package(path.parent, path.name)
    }
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    cache = PackageCache(workspace.models_path)
    from datetime import UTC, datetime

    for bearing in VALIDATION + HOLDOUT:
        for task, package_id in packages.items():
            store.create_binding(
                PhmBinding(
                    f"verify-{task.value}-{bearing}",
                    package_id,
                    "xjtu-sy-replay",
                    bearing,
                    cache.get(package_id).manifest.input.step_kind,
                    datetime.now(UTC),
                )
            )
        replay_xjtu_bearing(
            snapshots, args.source, asset_id=bearing, source_id="xjtu-sy-replay", interval_seconds=0
        )
    # Drain in pages so the run crosses many store connections and cursor commits.
    while any(
        cycle.results for cycle in run_snapshot_bindings(store, snapshots, cache, page_size=97)
    ):
        pass

    verdict: dict[str, Any] = {
        "protocol": "operational-inference-acceptance-protocol-v1",
        "checks": [],
    }
    anomaly_id = packages.get(ModelTask.ANOMALY_SCORE)
    if anomaly_id:
        verdict["checks"] += _anomaly_checks(store, cache, anomaly_id, args.evidence_root)
    verdict["checks"] += _sequential_batch_checks(store, cache, packages)
    verdict["pass"] = all(check["pass"] for check in verdict["checks"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for check in verdict["checks"]:
        print(f"{'PASS' if check['pass'] else 'FAIL'} {check['name']} {check.get('detail', '')}")
    print("VERDICT", "PASS" if verdict["pass"] else "FAIL")
    return 0 if verdict["pass"] else 1


def _analyzed(store: SqlitePhmAnalysisStore, binding_id: str) -> list[Any]:
    results = store.list_results(binding_id)
    skipped = [r for r in results if r.state is not StepState.ANALYZED]
    if skipped:
        raise SystemExit(f"{binding_id}: {len(skipped)} skipped steps, first: {skipped[0].reason}")
    return sorted(results, key=lambda r: r.position)


def _anomaly_checks(
    store: SqlitePhmAnalysisStore, cache: PackageCache, package_id: str, root: Path
) -> list[dict[str, Any]]:
    stored = json.loads((root / "xjtu-sy-iforest-fold-1-holdout-v1.json").read_text())
    checks = []
    for expected in stored["holdout_bearings"]:
        bearing = expected["asset_id"]
        results = _analyzed(store, f"verify-anomaly-score-{bearing}")
        scores = [float(r.output["score"]) for r in results]
        positions = [r.position for r in results]
        buckets: dict[str, list[float]] = defaultdict(list)
        for index, score in enumerate(scores):
            buckets[lifecycle_segment(index, len(scores))].append(score)
        rho = spearman_rho(positions, scores)
        late = late_vs_middle_rank_probability(
            tuple(buckets[MIDDLE_THIRD]), tuple(buckets[LATE_THIRD])
        )
        assert rho is not None and late is not None
        diff = max(
            abs(rho - expected["acquisition_order_spearman_rho"]),
            abs(late - expected["late_vs_middle_rank_probability"]),
        )
        checks.append(
            {
                "name": f"iforest-holdout-ranking-{bearing}",
                "pass": diff <= RHO_TOLERANCE
                and len(scores) == expected["full_run_observation_count"],
                "detail": f"rho={rho:.12f} late_vs_middle={late:.12f} max_abs_diff={diff:.3e}",
                "intervals": [
                    (i.start_position, i.end_position, i.open)
                    for i in store.list_intervals(f"verify-anomaly-score-{bearing}")
                ],
            }
        )
    return checks


def _sequential_batch_checks(
    store: SqlitePhmAnalysisStore, cache: PackageCache, packages: dict[ModelTask, str]
) -> list[dict[str, Any]]:
    checks = []
    for task, package_id in packages.items():
        package = cache.get(package_id)
        names = package.manifest.input.feature_names
        key = "score"
        worst = 0.0
        for bearing in VALIDATION + HOLDOUT:
            results = _analyzed(store, f"verify-{task.value}-{bearing}")
            rows = [[r.features[name] for name in names] for r in results if r.features]
            batch = package.evaluate(rows)
            worst = max(
                worst,
                max(abs(b - float(r.output[key])) for b, r in zip(batch, results, strict=True)),
            )
        checks.append(
            {
                "name": f"sequential-equals-batch-{task.value}",
                "pass": worst <= SEQUENTIAL_BATCH_TOLERANCE,
                "detail": f"max_abs_diff={worst:.3e}",
            }
        )
    return checks


if __name__ == "__main__":
    sys.exit(main())
