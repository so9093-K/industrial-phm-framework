"""Judge XJTU-SY LSTM packages against the acceptance protocol §2.3 and its v3 revision (§5).

LSTM training is not bit-reproducible across CPU math kernels. §2.3 judged retrained packages by
performance equivalence with the stored research evidence (per-bearing MAE within 2% relative
for RUL); that FAIL is preserved and reported as `pass_section_2_3`. The verdict of a run
(`pass` and the exit code) is §5 (v3): agreement with a same-environment research rerun,
determinism (sequential outputs equal a batch evaluation of the same package, <= 1e-4; the
causal input buffer survives restarts, every cycle here builds a fresh runner) and the
autoencoder Spearman rho within 0.05.
Without --research-rerun §5 cannot be judged and the run fails.

    uv run --no-sync python -m tools.phm.verify_xjtu_lstm <workspace-with-lstm-packages> \\
        --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets --output <verdict.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_runner import PackageCache, run_snapshot_bindings
from industrial_phm.demo.xjtu_snapshot_replay import replay_xjtu_bearing
from industrial_phm.experiments.xjtu_evaluation import spearman_rho
from industrial_phm.models.package import EstimatorKind, load_model_package
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

VALIDATION = ("Bearing1_2", "Bearing2_2", "Bearing3_2")
HOLDOUT = ("Bearing1_1", "Bearing2_1", "Bearing3_1")
MAE_RELATIVE = 0.02
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
            "directory with rul-validation.json, rul-benchmark.json and lstm-development.json "
            "from the research commands run in this same environment"
        ),
    )
    args = parser.parse_args(argv)
    workspace = OperationsWorkspace(args.workspace.resolve())
    kinds: dict[EstimatorKind, str] = {}
    for path in sorted(workspace.models_path.iterdir()):
        if (path / "package.json").is_file():
            kind = load_model_package(path).manifest.estimator_kind
            if kind in (EstimatorKind.LSTM_AUTOENCODER, EstimatorKind.LSTM_RUL):
                kinds[kind] = path.name
    if set(kinds) != {EstimatorKind.LSTM_AUTOENCODER, EstimatorKind.LSTM_RUL}:
        raise SystemExit("workspace needs one LSTM autoencoder and one LSTM RUL package")
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
    checks += _rul_checks(store, args.evidence_root, kinds[EstimatorKind.LSTM_RUL])
    checks += _autoencoder_checks(store, args.evidence_root)
    checks += _determinism_checks(store, workspace, kinds)
    same_environment = (
        _same_environment_checks(store, args.research_rerun) if args.research_rerun else []
    )
    verdict = {
        "protocol": "operational-inference-acceptance-protocol §2.3 (v1/v2) and §5 (v3)",
        "packages": {kind.value: package_id for kind, package_id in kinds.items()},
        "checks": checks,
        "same_environment_checks": same_environment,
        "pass_section_2_3": all(check["pass"] for check in checks),
        "pass_v3": bool(same_environment)
        and all(c["pass"] for c in same_environment)
        and all(c["pass"] for c in checks if not c["name"].startswith("lstm-rul-mae-")),
    }
    # One run, one meaning: the criterion in force for LSTM packages (§5, v3) decides `pass` and
    # the exit code. §2.3 stays a separate, preserved record and is never folded into it.
    verdict["pass"] = verdict["pass_v3"]
    verdict["pass_criterion"] = (
        "§5 (v3) operational reproducibility; requires --research-rerun. "
        "pass_section_2_3 is the preserved v1/v2 performance-equivalence record, not part of pass"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for check in checks + same_environment:
        print(f"{'PASS' if check['pass'] else 'FAIL'} {check['name']} {check.get('detail', '')}")
    print("RECORD §2.3 (v1/v2, preserved)", "PASS" if verdict["pass_section_2_3"] else "FAIL")
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


def _rul_checks(store: SqlitePhmAnalysisStore, root: Path, package_id: str) -> list[dict[str, Any]]:
    validation = json.loads(
        (root / "xjtu-sy-rul-three-model-fold-1-validation-v1.json").read_text()
    )
    method = next(
        m for m in validation["methods"] if m["method_id"] == "xjtu-sy-rul-lstm-fold-1-v1"
    )
    benchmark = json.loads((root / "xjtu-sy-rul-lstm-fold-1-benchmark-v1.json").read_text())
    stored = {b["asset_id"]: b["mean_absolute_error"] for b in method["evaluation"]["bearings"]}
    stored.update(
        {
            b["asset_id"]: b["mean_absolute_error"]
            for b in benchmark["evaluation"]["point"]["bearings"]
        }
    )
    checks = []
    for bearing in VALIDATION + HOLDOUT:
        analyzed, _ = _steps(store, f"lstm-lstm-rul-v1-{bearing}")
        total = get_xjtu_expected_acquisition_count(bearing)
        mae = sum(abs(float(r.output["estimate"]) - (total - r.position)) for r in analyzed) / len(
            analyzed
        )
        relative = abs(mae - stored[bearing]) / stored[bearing]
        checks.append(
            {
                "name": f"lstm-rul-mae-{bearing}",
                "pass": relative <= MAE_RELATIVE and len(analyzed) == total - 7,
                "detail": (
                    f"operational={mae:.3f} stored={stored[bearing]:.3f} relative={relative:.4f}"
                ),
            }
        )
    return checks


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
        key = "score" if kind is EstimatorKind.LSTM_AUTOENCODER else "estimate"
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
    validation = json.loads((rerun / "rul-validation.json").read_text())
    benchmark = json.loads((rerun / "rul-benchmark.json").read_text())
    development = json.loads((rerun / "lstm-development.json").read_text())
    method = next(
        m for m in validation["methods"] if m["method_id"] == "xjtu-sy-rul-lstm-fold-1-v1"
    )
    research_rul = {
        (series["asset_id"], item["acquisition_index"]): item["predicted_remaining_useful_life"]
        for series in method["predictions"]
        + benchmark["method"].get("predictions", [])
        + benchmark.get("predictions", [])
        for item in series["observations"]
    }
    research_ae = {
        (trajectory["asset_id"], item["acquisition_index"]): item["score"]
        for trajectory in development["scoring"]["trajectories"]
        for item in trajectory["observations"]
    }
    checks = []
    for kind, research, key in (
        ("lstm-rul-v1", research_rul, "estimate"),
        ("lstm-autoencoder-v1", research_ae, "score"),
    ):
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
