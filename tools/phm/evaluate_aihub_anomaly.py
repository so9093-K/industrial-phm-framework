"""Run the AI-Hub 239 air-compressor anomaly acceptance evaluation (protocol v1 §3).

Stage 1 (development devices): fit both candidates per device, measure, select one.
Stage 2 (evaluation devices): fit only the selected candidate per device, measure once, judge.

    uv run --no-sync python -m tools.phm.evaluate_aihub_anomaly \\
        data/raw/aihub/239/archives/training/raw/3.공기압축기.zip --output <result.json>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from industrial_phm.adapters.aihub_power import archive_sha256, list_power_members
from industrial_phm.experiments import aihub_electrical_anomaly as ev

CANDIDATES = ("isolation-forest", "pca-residual")
REFERENCE_MEMBER = "3.공기압축기/SourceData_16.json"
GATE_RATE = 0.90
ALARM_LIMIT = 0.02


def _evaluate_member(job: tuple[str, str, str, tuple[str, ...], str]) -> dict[str, Any]:
    archive, digest, member, candidates, revision = job
    device = ev.load_device(Path(archive), member, archive_sha256=digest)
    report: dict[str, Any] = {"member": member, "device_id": device.device_id}
    if device.ineligible_reason:
        return {**report, "eligible": False, "reason": device.ineligible_reason}
    train, holdout, boundary = ev.split_device(device.samples)
    counts = (ev.running_count(train), ev.running_count(holdout))
    report.update(boundary=boundary.isoformat(), train_running=counts[0], holdout_running=counts[1])
    if counts[0] < ev.MIN_TRAIN_RUNNING or counts[1] < ev.MIN_HOLDOUT_RUNNING:
        return {**report, "eligible": False, "reason": "insufficient running timestamps"}
    report["eligible"] = True
    if not candidates:
        return report
    train_rows, holdout_rows = ev.window_rows(train), ev.window_rows(holdout)
    report["windows"] = {
        "train_evaluated": sum(1 for r in train_rows if r.features),
        "train_not_evaluated": sum(1 for r in train_rows if not r.features),
        "holdout_evaluated": sum(1 for r in holdout_rows if r.features),
        "holdout_not_evaluated": sum(1 for r in holdout_rows if not r.features),
    }
    report["candidates"] = {}
    with tempfile.TemporaryDirectory() as models:
        for candidate in candidates:
            package = ev.build_device_package(
                candidate,
                train_rows,
                Path(models),
                device=device,
                boundary=boundary,
                created_at=datetime(2026, 10, 12, tzinfo=UTC),
                code_revision=revision,
            )
            threshold = float(package.manifest.output.threshold or 0.0)
            inside, evaluated = ev.alarm_window_fraction(
                ev.score_rows(package, holdout_rows), threshold
            )
            rng = random.Random(f"{ev.SEED}:{member}")
            injections = []
            for injection in ev.INJECTIONS:
                for index, start in enumerate(
                    ev.injection_starts(
                        holdout_rows, rng, ev.INJECTIONS_PER_TYPE, injection.duration
                    )
                ):
                    injections.append(
                        ev.evaluate_injection(package, holdout, injection, start, phase=index % 3)
                    )
            report["candidates"][candidate] = {
                "package_id": package.package_id,
                "threshold": threshold,
                "holdout_alarm_windows": inside,
                "holdout_evaluated_windows": evaluated,
                "holdout_alarm_fraction": inside / evaluated if evaluated else None,
                "injections": injections,
            }
    return report


def _rates(reports: list[dict[str, Any]], candidate: str) -> dict[str, Any]:
    per_kind: dict[str, list[float]] = {}
    delays: dict[str, list[float]] = {}
    for report in reports:
        results = report["candidates"][candidate]["injections"]
        for injection in ev.INJECTIONS:
            items = [r for r in results if r["kind"] == injection.kind]
            if items:
                per_kind.setdefault(injection.kind, []).append(
                    fmean(1.0 if r["detected"] else 0.0 for r in items)
                )
                delays.setdefault(injection.kind, []).extend(
                    r["delay_minutes"] for r in items if r["detected"]
                )
    alarm = [
        r["candidates"][candidate]["holdout_alarm_fraction"]
        for r in reports
        if r["candidates"][candidate]["holdout_alarm_fraction"] is not None
    ]
    return {
        "devices": len(reports),
        "detection_rate": {kind: fmean(values) for kind, values in per_kind.items()},
        "median_delay_minutes": {
            kind: sorted(v)[len(v) // 2] if v else None for kind, v in delays.items()
        },
        "holdout_alarm_fraction": fmean(alarm) if alarm else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-revision", default="0" * 40)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--stage",
        choices=("development", "evaluation"),
        default="evaluation",
        help="development stops after candidate selection; evaluation devices are judged once",
    )
    args = parser.parse_args(argv)

    digest = archive_sha256(args.archive)
    members = list_power_members(args.archive)
    print(f"archive members={len(members)} sha256={digest[:12]}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        screening = list(
            pool.map(
                _evaluate_member,
                [(str(args.archive), digest, m, (), args.code_revision) for m in members],
            )
        )
    eligible = [r["member"] for r in screening if r.get("eligible")]
    print(f"eligible={len(eligible)} of {len(members)}", flush=True)
    development = ev.choose_development_members(eligible, REFERENCE_MEMBER)
    evaluation = [m for m in eligible if m not in development]

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        dev_reports = list(
            pool.map(
                _evaluate_member,
                [
                    (str(args.archive), digest, m, CANDIDATES, args.code_revision)
                    for m in development
                ],
            )
        )
    dev_summary = {candidate: _rates(dev_reports, candidate) for candidate in CANDIDATES}
    gate_kinds = [i.kind for i in ev.INJECTIONS if i.gate]

    def gate_mean(candidate: str) -> float:
        return fmean(dev_summary[candidate]["detection_rate"].get(k, 0.0) for k in gate_kinds)

    scores = {candidate: gate_mean(candidate) for candidate in CANDIDATES}
    best = max(scores.values())
    tied = [c for c in CANDIDATES if best - scores[c] <= 0.005]
    selected = "pca-residual" if "pca-residual" in tied else tied[0]
    print(f"development gate means={scores} selected={selected}", flush=True)
    if args.stage == "development":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "stage": "development",
                    "development_members": development,
                    "development_summary": dev_summary,
                    "development_gate_means": scores,
                    "selected_candidate": selected,
                    "eligible_count": len(eligible),
                    "evaluation_member_count": len(evaluation),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps(dev_summary, ensure_ascii=False, indent=2))
        return 0

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        eval_reports = list(
            pool.map(
                _evaluate_member,
                [
                    (str(args.archive), digest, m, (selected,), args.code_revision)
                    for m in evaluation
                ],
            )
        )
    final = _rates(eval_reports, selected)
    checks = {kind: final["detection_rate"].get(kind, 0.0) >= GATE_RATE for kind in gate_kinds}
    alarm_ok = (
        final["holdout_alarm_fraction"] is not None
        and final["holdout_alarm_fraction"] <= ALARM_LIMIT
    )
    verdict = all(checks.values()) and alarm_ok
    result = {
        "schema_id": "aihub-239-air-compressor-electrical-anomaly-evaluation-v1",
        "protocol": "docs/research/operational-inference-acceptance-protocol.md §3 (v1)",
        "archive_sha256": digest,
        "code_revision": args.code_revision,
        "feature_set_id": "electrical-window-v1",
        "screening": [
            {
                k: v
                for k, v in r.items()
                if k
                in {"member", "device_id", "eligible", "reason", "train_running", "holdout_running"}
            }
            for r in screening
        ],
        "development_members": development,
        "development_summary": dev_summary,
        "development_gate_means": scores,
        "selected_candidate": selected,
        "evaluation_members": evaluation,
        "evaluation_summary": final,
        "checks": {"detection_rate_ge_0.90": checks, "holdout_alarm_fraction_le_0.02": alarm_ok},
        "pass": verdict,
        "development_reports": dev_reports,
        "evaluation_reports": eval_reports,
        "limitations": [
            "No provider label is ground truth; the unmodified-data alarm fraction may include "
            "real changes.",
            "Injected changes are synthetic edits of recorded values, not physical faults.",
            "Timezone Asia/Seoul is a configured assumption; device identity is the provider "
            "DEVICE_ID.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "selected": selected,
                "evaluation": final,
                "checks": result["checks"],
                "pass": verdict,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
