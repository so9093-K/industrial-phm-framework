"""M5/M7 product acceptance: XJTU-SY recorded replay through the real supervised node.

One workspace, one continuous journey:

    packages -> explicit bindings -> supervisor -> 1 s acquisition replay (latency measured)
    -> supervisor stop while delivery continues -> restart and catch-up -> gap -> duplicates
    -> incompatible input and unloadable package -> Web screens -> real local-main explanation
    -> human review -> restart -> everything persisted

    uv run --no-sync --with playwright python -m tools.phm.acceptance_xjtu \\
        --source data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets \\
        --lstm-models artifacts/phm-lstm/models --output artifacts/acceptance/xjtu
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    SqliteAcquisitionSnapshotRepository,
    file_sha256,
)
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.features.vibration import vibration_feature_names
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    write_model_package,
)
from tools.phm.acceptance_common import (
    CLI,
    NOT_CAUGHT_UP,
    Checks,
    Supervisor,
    check_explanation,
    cli,
    displayed,
    free_port,
    percentiles,
    record_display,
    reflection_latency,
    set_config,
    wait_until,
    write_evidence,
)

SOURCE_ID = "xjtu-sy-replay"
BEARING = "Bearing1_1"  # fold-1 held-out bearing, 123 acquisitions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--lstm-models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    workspace = output / "ws"
    checks = Checks()
    evidence: dict[str, Any] = {
        "scenario": "xjtu-sy-recorded-replay-product-acceptance",
        "started_at": datetime.now(UTC).isoformat(),
        "code_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip(),
    }

    # 1. Workspace, packages, explicit bindings ------------------------------------------
    cli("operations", "init", str(workspace))
    port = free_port()
    set_config(workspace, "ui", "port", str(port))
    built = cli(
        "operations",
        "phm",
        "package-xjtu",
        str(workspace),
        "--source",
        str(args.source),
        "--code-revision",
        evidence["code_revision"] or "0" * 40,
    )
    packages = {
        line.split()[1].split("=")[1]: line.split()[0].split("=")[1]
        for line in built.splitlines()
        if line.startswith("package=")
    }
    for path in sorted(args.lstm_models.iterdir()):
        if (path / "package.json").is_file():
            shutil.copytree(path, workspace / "models" / path.name)
            kind = json.loads((path / "package.json").read_text())["estimator_kind"]
            packages["lstm-" + kind] = path.name
    evidence["packages"] = packages
    bindings: dict[str, str] = {}
    for name, package_id in packages.items():
        binding_id = f"{name}-{BEARING}"
        cli(
            "operations",
            "phm",
            "bind",
            str(workspace),
            "--package",
            package_id,
            "--source-id",
            SOURCE_ID,
            "--asset-id",
            BEARING,
            "--binding-id",
            binding_id,
            "--recorded-replay",
        )
        bindings[name] = binding_id
    evidence["bindings"] = bindings
    anomaly_binding, rul_binding = bindings["anomaly-score"], bindings["rul-estimate"]

    # Incompatible input: the IForest package on a stream with other channels and sampling.
    foreign = output / "foreign"
    foreign.mkdir()
    csv = foreign / "1.csv"
    csv.write_text("x,y\n" + "\n".join(f"{i % 5},{i % 3}" for i in range(64)) + "\n")
    cli(
        "operations",
        "phm",
        "bind",
        str(workspace),
        "--package",
        packages["anomaly-score"],
        "--source-id",
        "foreign-sensor",
        "--asset-id",
        "pump-x",
        "--binding-id",
        "foreign-pump-x",
    )
    # Unloadable package: valid at bind time, its payload changes before the runner loads it.
    names = vibration_feature_names(("h", "v"))
    broken = write_model_package(
        workspace / "models",
        PackageBuild(
            recipe_id="acceptance-tampered-v1",
            estimator_kind=EstimatorKind.LINEAR,
            input=PackageInputSpec(
                step_kind=StepKind.ACQUISITION_SNAPSHOT,
                channels=("h", "v"),
                feature_set_id="vibration-statistical-v1",
                feature_names=names,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="score",
                threshold=1.0,
                threshold_rule="fixed",
                review_interval=ReviewIntervalRule(2, 1),
            ),
            preprocessing=AffinePreprocessing((0.0,) * len(names), (1.0,) * len(names)),
            estimator_state={"coefficients": [0.1] * len(names), "intercept": 0.0},
            fit_rows=None,
            probe_rows=[[1.0] * len(names)],
            training_scope={},
            validation={},
            applicability={},
            created_at=datetime.now(UTC).isoformat(),
            code_revision="0" * 40,
        ),
    )
    cli(
        "operations",
        "phm",
        "bind",
        str(workspace),
        "--package",
        broken.package_id,
        "--source-id",
        "foreign-sensor",
        "--asset-id",
        "pump-y",
        "--binding-id",
        "tampered-pump-y",
    )
    state_path = workspace / "models" / broken.package_id / "state.json"
    state_path.write_text(state_path.read_text().replace('"intercept":0.0', '"intercept":9.0'))

    store = SqlitePhmAnalysisStore(workspace / "phm-analysis.sqlite")
    snapshots = SqliteAcquisitionSnapshotRepository(workspace / "snapshots.sqlite")
    supervisor = Supervisor(workspace, output / "supervisor.log")

    def replay(start: int, count: int, interval: float) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [
                *CLI,
                "operations",
                "phm",
                "replay-xjtu",
                str(workspace),
                "--source",
                str(args.source),
                "--bearing",
                BEARING,
                "--source-id",
                SOURCE_ID,
                "--start",
                str(start),
                "--count",
                str(count),
                "--interval-seconds",
                str(interval),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def results(binding: str) -> list[Any]:
        return sorted(store.list_results(binding), key=lambda r: r.position)

    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="ko-KR")
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        url = f"http://127.0.0.1:{port}/web/"
        try:
            # 2. Live replay with latency measurement -----------------------------------
            evidence["supervisor_ready_seconds"] = [supervisor.start()]
            SqliteAcquisitionSnapshotRepository(workspace / "snapshots.sqlite").record(
                AcquisitionSnapshot(
                    source_id="foreign-sensor",
                    asset_id="pump-x",
                    ordinal=1,
                    file_path=csv.resolve(),
                    sha256=file_sha256(csv),
                    channels=("x", "y"),
                    sampling_rate_hz=1000.0,
                    sample_count=64,
                    delivered_at=datetime.now(UTC),
                    replay=True,
                )
            )
            valid = foreign / "valid.csv"
            valid.write_text(
                "h,v\n" + "\n".join(f"{i % 5 - 2},{i % 3 - 1}" for i in range(64)) + "\n"
            )
            SqliteAcquisitionSnapshotRepository(workspace / "snapshots.sqlite").record(
                AcquisitionSnapshot(
                    source_id="foreign-sensor",
                    asset_id="pump-y",
                    ordinal=1,
                    file_path=valid.resolve(),
                    sha256=file_sha256(valid),
                    channels=("h", "v"),
                    sampling_rate_hz=1000.0,
                    sample_count=64,
                    delivered_at=datetime.now(UTC),
                    replay=True,
                )
            )
            page.goto(url + "#anomaly")
            page.select_option("#anomaly-binding", anomaly_binding)
            record_display(page, "anomaly-freshness")
            live = replay(1, 30, 1.0)
            evidence["phase_live_replay"] = live.communicate()[0].splitlines()[-1]

            # 3. Supervisor stop while delivery continues, then restart ------------------
            evidence["supervisor_stop_seconds"] = supervisor.stop()
            down = replay(31, 15, 0.2)
            down.communicate()
            backlog_at_restart = len(snapshots.list_after(SOURCE_ID, BEARING, after_ordinal=30))
            evidence["supervisor_ready_seconds"].append(supervisor.start())
            caught_up = wait_until(lambda: _latest(store, anomaly_binding) >= 45, timeout=120)
            checks.add("restart-catches-up-backlog", caught_up, f"backlog={backlog_at_restart}")
            live2 = replay(46, 15, 1.0)
            live2.communicate()
            time.sleep(5)  # one more screen poll after the last live commit
            shown = [
                (at, int(match.group(1)))
                for at, text in displayed(page)
                if (match := re.search(r"최신 분석 #(\d+) ", text))
            ]
            # 4. Gap and duplicate delivery ---------------------------------------------
            replay(62, 8, 0.5).communicate()
            duplicate = replay(1, 10, 0.0).communicate()[0]
            checks.add(
                "duplicate-delivery-is-ignored",
                "delivered=0 already_present=10" in duplicate,
                duplicate.splitlines()[-1],
            )
            wait_until(lambda: all(_latest(store, b) >= 69 for b in bindings.values()), timeout=120)

            # 5. Exactly-once, gaps and latency ------------------------------------------
            delivered = {
                s.ordinal: s
                for s in snapshots.list_after(SOURCE_ID, BEARING, after_ordinal=None, limit=1000)
            }
            expected = set(range(1, 61)) | set(range(62, 70))
            checks.add(
                "delivered-acquisitions",
                set(delivered) == expected,
                sorted(set(delivered) ^ expected),
            )
            supply_latency: dict[str, list[float]] = {}
            for name, binding in bindings.items():
                rows = results(binding)
                positions = [r.position for r in rows]
                checks.add(
                    f"exactly-once-{name}",
                    sorted(positions) == sorted(expected) and len(positions) == len(set(positions)),
                    {
                        "results": len(positions),
                        "analyzed": sum(r.state is StepState.ANALYZED for r in rows),
                    },
                )
                live_positions = set(range(1, 31)) | set(range(46, 61)) | set(range(62, 70))
                supply_latency[name] = [
                    (r.processed_at - delivered[r.position].delivered_at).total_seconds()
                    for r in rows
                    if r.position in live_positions
                ]
                if name.startswith("lstm"):
                    warmups = [
                        r.position for r in rows if (r.reason or "").startswith("sequence warm-up")
                    ]
                    checks.add(
                        f"sequence-survives-restart-and-restarts-after-gap-{name}",
                        warmups == list(range(1, 8)) + list(range(62, 69)),
                        warmups,
                    )
            evidence["supply_to_commit_seconds"] = {
                k: percentiles(v) for k, v in supply_latency.items()
            }
            for name in ("anomaly-score", "rul-estimate"):
                p95 = evidence["supply_to_commit_seconds"][name]["p95"]
                checks.add(
                    f"supply-to-commit-p95-le-2s-{name}", p95 is not None and p95 <= 2.0, p95
                )
            measured = [
                (r.position, r.processed_at)
                for r in results(anomaly_binding)
                if r.position in set(range(1, 31)) | set(range(46, 61))
            ]
            screen_latency, not_caught_up = reflection_latency(measured, shown)
            evidence["commit_to_screen_seconds"] = {
                **percentiles(screen_latency),
                "not_caught_up": not_caught_up,
                "not_caught_up_meaning": NOT_CAUGHT_UP,
                "screen_poll_ms": 3000,
            }
            checks.add("screen-caught-up-after-every-commit", not_caught_up == 0, not_caught_up)
            p95 = evidence["commit_to_screen_seconds"]["p95"]
            checks.add("commit-to-screen-p95-le-5s", p95 is not None and p95 <= 5.0, p95)

            # 6. Rejections reach the screen ---------------------------------------------
            page.reload()
            page.select_option("#anomaly-binding", "foreign-pump-x")
            expect(page.locator("#anomaly-state")).to_contain_text(
                "입력을 분석할 수 없습니다", timeout=15_000
            )
            checks.add(
                "incompatible-input-reason-on-screen",
                "channels differ" in page.locator("#anomaly-state").inner_text(),
                page.locator("#anomaly-state").inner_text(),
            )
            page.select_option("#anomaly-binding", "tampered-pump-y")
            expect(page.locator("#anomaly-state")).to_contain_text(
                "모델을 실행할 수 없습니다", timeout=15_000
            )
            checks.add(
                "unloadable-package-on-screen", True, page.locator("#anomaly-state").inner_text()
            )
            checks.add(
                "unloadable-package-produces-no-results",
                store.list_results("tampered-pump-y") == (),
                len(store.list_results("tampered-pump-y")),
            )

            # 7. Real local-main explanation and human review ----------------------------
            explanations: dict[str, Any] = {}
            for view, binding in (("anomaly", anomaly_binding), ("rul", rul_binding)):
                page.goto(url + "#" + view)
                page.select_option(f"#{view}-binding", binding)
                panel = page.locator(f"#{view}-explanation")
                expect(panel).to_contain_text("사람 검토", timeout=15_000)
                page.locator("#anomaly-review-options > summary").click()
                panel.locator(".phm-ai-details summary").click()
                panel.get_by_role("button", name="AI 설명 생성").click()
                expect(panel.locator(".phm-ai-text")).not_to_be_empty(timeout=180_000)
                explanations[view] = check_explanation(checks, f"-{view}", panel, window=False)
                panel.get_by_role("button", name="검토 요청").click()
                expect(panel.locator(".phm-review-history")).to_contain_text("검토 요청됨")
                panel.get_by_label("검토 메모").first.fill(f"{view}: 원본 파형과 추세를 확인함")
                panel.get_by_role("button", name="검토 확인").click()
                expect(panel.locator(".phm-review-history")).to_contain_text("검토 확인됨")
                panel.get_by_role("button", name="검토 종료").click()
                expect(panel.locator(".phm-review-history")).to_contain_text("검토 완료")
                page.screenshot(path=str(output / f"{view}-reviewed.png"), full_page=True)
            evidence["explanations"] = explanations

            # 8. Restart: results, explanation and review persist ------------------------
            before = {b: len(store.list_results(b)) for b in bindings.values()}
            supervisor.stop()
            evidence["supervisor_ready_seconds"].append(supervisor.start())
            time.sleep(3)
            after = {b: len(store.list_results(b)) for b in bindings.values()}
            checks.add("restart-keeps-results-unchanged", before == after, after)
            for view, binding in (("anomaly", anomaly_binding), ("rul", rul_binding)):
                page.goto(url + "#" + view)
                page.select_option(f"#{view}-binding", binding)
                panel = page.locator(f"#{view}-explanation")
                expect(panel.locator(".phm-ai-text")).to_have_text(
                    explanations[view]["text"], timeout=15_000
                )
                expect(panel.locator(".phm-review-history")).to_contain_text("검토 완료")
                checks.add(f"restart-keeps-explanation-and-review-{view}", True)
                page.screenshot(path=str(output / f"{view}-after-restart.png"), full_page=True)
            checks.add("no-browser-errors", not errors, errors)
        finally:
            browser.close()
            if supervisor.process is not None and supervisor.process.poll() is None:
                supervisor.stop()

    evidence["checks"] = checks.items
    evidence["pass"] = checks.passed
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    write_evidence(output / "evidence.json", evidence)
    print("VERDICT", "PASS" if checks.passed else "FAIL")
    return 0 if checks.passed else 1


def _latest(store: SqlitePhmAnalysisStore, binding: str) -> int:
    result = store.latest_result(binding)
    return 0 if result is None else result.position


if __name__ == "__main__":
    sys.exit(main())
