"""Judge the XJTU-SY LSTM autoencoder package against the acceptance protocol §5 (v3).

LSTM training is not bit-reproducible across CPU math kernels. The verdict of a run (`pass` and
the exit code) is §5 (v3): agreement with a same-environment research rerun, determinism
(sequential outputs equal a batch evaluation of the same package, <= 1e-4; the causal input
buffer survives restarts, every cycle here builds a fresh runner) and the autoencoder Spearman
rho within 0.05. Remaining-life packages were retired and are no longer judged.
Without --research-rerun §5 cannot be judged and the run fails.

    uv run --no-sync python -m tools.phm.verify_xjtu_lstm <workspace-with-lstm-packages> \\
        --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \\
        --research-rerun <same-environment-research-rerun-dir> --output <verdict.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_runner import PackageCache, run_snapshot_bindings
from industrial_phm.demo.xjtu_snapshot_replay import replay_xjtu_bearing
from industrial_phm.experiments.xjtu_evaluation import spearman_rho
from industrial_phm.models.package import EstimatorKind, load_model_package
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

VALIDATION = ("Bearing1_2", "Bearing2_2", "Bearing3_2")
HOLDOUT = ("Bearing1_1", "Bearing2_1", "Bearing3_1")
RHO_ABSOLUTE = 0.05
SEQUENTIAL_BATCH = 1e-4
_RESULTS = Path("docs/research/results")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, default=_RESULTS)
    parser.add_argument(
        "--research-rerun",
        type=Path,
        help=(
            "directory with lstm-development.json from the research command run in this "
            "same environment"
        ),
    )
    args = parser.parse_args(argv)
    workspace = OperationsWorkspace(args.workspace.resolve())
    kinds: dict[EstimatorKind, str] = {}
    for path in sorted(workspace.models_path.iterdir()):
        if (path / "package.json").is_file():
            kind = load_model_package(path).manifest.estimator_kind
            if kind is EstimatorKind.LSTM_AUTOENCODER:
                kinds[kind] = path.name
    if set(kinds) != {EstimatorKind.LSTM_AUTOENCODER}:
        raise SystemExit("workspace needs one LSTM autoencoder package")
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    for bearing in VALIDATION + HOLDOUT:
        for kind, package_id in kinds.items():
            store.create_binding(
                PhmBinding(
                    f"lstm-{kind.value}-{bearing}",
                    package_id,
                    "xjtu-sy-replay",
                    bearing,
                    load_model_package(workspace.models_path / package_id).manifest.input.step_kind,
                    datetime.now(UTC),
                )
            )
        replay_xjtu_bearing(
            snapshots, args.source, asset_id=bearing, source_id="xjtu-sy-replay", interval_seconds=0
        )
    cycles = 0
    while True:
        # A fresh package cache and store per cycle: state must come back from disk.
        fresh_store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
        results = run_snapshot_bindings(
            fresh_store, snapshots, PackageCache(workspace.models_path), page_size=211
        )
        cycles += 1
        if not any(cycle.results for cycle in results):
            break

    checks: list[dict[str, Any]] = [{"name": "runner-restarts", "pass": True, "detail": cycles}]
    checks += _autoencoder_checks(store, args.evidence_root)
    checks += _determinism_checks(store, workspace, kinds)
    same_environment = (
        _same_environment_checks(store, args.research_rerun) if args.research_rerun else []
    )
    verdict = {
        "protocol": "operational-inference-acceptance-protocol §5 (v3)",
        "packages": {kind.value: package_id for kind, package_id in kinds.items()},
        "checks": checks,
        "same_environment_checks": same_environment,
        "pass_v3": bool(same_environment)
        and all(c["pass"] for c in same_environment)
        and all(c["pass"] for c in checks),
    }
    verdict["pass"] = verdict["pass_v3"]
    verdict["pass_criterion"] = "§5 (v3) operational reproducibility; requires --research-rerun."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for check in checks + same_environment:
        print(f"{'PASS' if check['pass'] else 'FAIL'} {check['name']} {check.get('detail', '')}")
    if same_environment:
        print("VERDICT §5 (v3)", "PASS" if verdict["pass_v3"] else "FAIL")
    else:
        print("VERDICT §5 (v3) NOT JUDGED: --research-rerun is required")
    return 0 if verdict["pass"] else 1


def _steps(store: SqlitePhmAnalysisStore, binding_id: str) -> tuple[list[Any], list[Any]]:
    results = sorted(store.list_results(binding_id), key=lambda r: r.position)
    analyzed = [r for r in results if r.state is StepState.ANALYZED]
    skipped = [r for r in results if r.state is not StepState.ANALYZED]
    return analyzed, skipped


def _autoencoder_checks(store: SqlitePhmAnalysisStore, root: Path) -> list[dict[str, Any]]:
    development = json.loads(
        (root / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json").read_text()
    )
    stored = {
        b["asset_id"]: b["acquisition_order_spearman_rho"]
        for b in development["evaluation"]["bearings"]
    }
    checks = []
    for bearing in VALIDATION:
        analyzed, _ = _steps(store, f"lstm-lstm-autoencoder-v1-{bearing}")
        rho = spearman_rho(
            [r.position for r in analyzed], [float(r.output["score"]) for r in analyzed]
        )
        assert rho is not None
        diff = abs(rho - stored[bearing])
        checks.append(
            {
                "name": f"lstm-autoencoder-rho-{bearing}",
                "pass": diff <= RHO_ABSOLUTE,
                "detail": f"operational={rho:.4f} stored={stored[bearing]:.4f} diff={diff:.4f}",
            }
        )
    return checks


def _determinism_checks(
    store: SqlitePhmAnalysisStore, workspace: OperationsWorkspace, kinds: dict[EstimatorKind, str]
) -> list[dict[str, Any]]:
    checks = []
    for kind, package_id in kinds.items():
        package = load_model_package(workspace.models_path / package_id)
        names = package.manifest.input.feature_names
        key = "score"
        worst, warmups, gaps = 0.0, set(), 0
        for bearing in VALIDATION + HOLDOUT:
            analyzed, skipped = _steps(store, f"lstm-{kind.value}-{bearing}")
            warmups.add(sum(1 for r in skipped if (r.reason or "").startswith("sequence warm-up")))
            features = {
                r.position: [r.features[n] for n in names] for r in analyzed + skipped if r.features
            }
            rows, observed = [], []
            for result in analyzed:
                positions = result.output["sequence_positions"]
                if positions != list(
                    range(result.position - len(positions) + 1, result.position + 1)
                ):
                    gaps += 1
                rows.append([v for p in positions for v in features[p]])
                observed.append(float(result.output[key]))
            batch = package.evaluate(rows)
            worst = max(worst, max(abs(a - b) for a, b in zip(batch, observed, strict=True)))
        checks.append(
            {
                "name": f"sequential-equals-batch-{kind.value}",
                "pass": worst <= SEQUENTIAL_BATCH and gaps == 0 and warmups == {7},
                "detail": (
                    f"max_abs_diff={worst:.3e} non_contiguous={gaps} "
                    f"warmups_per_bearing={sorted(warmups)}"
                ),
            }
        )
    return checks


def _same_environment_checks(store: SqlitePhmAnalysisStore, rerun: Path) -> list[dict[str, Any]]:
    """Operational outputs versus the research pipeline rerun in this same environment."""
    development = json.loads((rerun / "lstm-development.json").read_text())
    research_ae = {
        (trajectory["asset_id"], item["acquisition_index"]): item["score"]
        for trajectory in development["scoring"]["trajectories"]
        for item in trajectory["observations"]
    }
    checks = []
    for kind, research, key in (("lstm-autoencoder-v1", research_ae, "score"),):
        worst, compared = 0.0, 0
        for bearing in VALIDATION + HOLDOUT:
            analyzed, _ = _steps(store, f"lstm-{kind}-{bearing}")
            for result in analyzed:
                expected = research.get((bearing, result.position))
                if expected is not None:
                    compared += 1
                    worst = max(worst, abs(float(result.output[key]) - float(expected)))
        checks.append(
            {
                "name": f"same-environment-research-rerun-{kind}",
                "pass": compared > 0 and worst <= SEQUENTIAL_BATCH,
                "detail": f"compared={compared} max_abs_diff={worst:.3e}",
            }
        )
    return checks


if __name__ == "__main__":
    sys.exit(main())
