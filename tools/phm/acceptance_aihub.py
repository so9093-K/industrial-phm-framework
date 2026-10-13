"""M5/M7 product acceptance: AI-Hub 239 air-compressor OPC UA replay through the real node.

One workspace, one continuous journey on device 1338's held-out period:

    replay source -> per-device PCA package -> explicit binding -> supervisor -> OPC UA replay
    with original timestamps (window latency measured) -> supervisor stop/restart while the
    replay keeps publishing (a real collection gap) -> Web -> real local-main explanation ->
    human review -> restart -> everything persisted; RUL screen states that no RUL applies

    uv run --no-sync --with playwright python -m tools.phm.acceptance_aihub \\
        --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip \\
        --output artifacts/acceptance/aihub
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    initialize_operations_workspace,
)
from tools.phm.acceptance_common import (
    Checks,
    Supervisor,
    cli,
    displayed,
    free_port,
    percentiles,
    record_display,
    reflection_latency,
    set_config,
    write_evidence,
)

MEMBER = "3.공기압축기/SourceData_16.json"
SOURCE_ID = "aihub239-replay-air-compressor-1338"
ASSET_ID = "aihub-air-compressor-1338"
# Held-out period of device 1338 (training is the first 70% of its record, before 09:35 local).
START, END, SPEED = "2020-11-13T09:35:00", "2020-11-13T13:35:00", 60


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    workspace = output / "ws"
    checks = Checks()
    evidence: dict[str, Any] = {
        "scenario": "aihub-239-air-compressor-opcua-replay-product-acceptance",
        "started_at": datetime.now(UTC).isoformat(),
        "selection": {"member": MEMBER, "start_local": START, "end_local": END, "speed": SPEED},
        "code_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip(),
    }

    # 1. Replay source, workspace, package, binding --------------------------------------
    opcua_port = free_port()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.opcua.aihub_replay",
            "prepare",
            "--root",
            str(workspace),
            "--endpoint",
            f"opc.tcp://127.0.0.1:{opcua_port}/phm/",
            "--archive",
            str(args.archive),
            "--member",
            MEMBER,
            "--binding",
            "tools/opcua/presets/aihub-air-compressor-1338-replay.json",
            "--start",
            START,
            "--end",
            END,
        ],
        check=True,
        capture_output=True,
    )
    initialize_operations_workspace(OperationsWorkspace(workspace), allow_recognized_legacy=True)
    ui_port = free_port()
    set_config(workspace, "ui", "port", str(ui_port))
    set_config(workspace, "collection", "window_duration_seconds", "300.0")
    built = cli(
        "operations",
        "phm",
        "package-aihub",
        str(workspace),
        "--archive",
        str(args.archive),
        "--member",
        MEMBER,
        "--candidate",
        "pca-residual",
    )
    package_id = next(
        line.split()[0].split("=")[1] for line in built.splitlines() if line.startswith("package=")
    )
    evidence["package_id"] = package_id
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
        ASSET_ID,
        "--binding-id",
        "aihub-1338",
        "--recorded-replay",
    )
    cli(
        "internal",
        "request-collection",
        "--workspace",
        str(workspace),
        "--source-id",
        SOURCE_ID,
        "--state",
        "running",
    )
    store = SqlitePhmAnalysisStore(workspace / "phm-analysis.sqlite")
    windows = SqliteObservationWindowRepository(workspace / "windows.sqlite")
    supervisor = Supervisor(workspace, output / "supervisor.log")

    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="ko-KR")
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        url = f"http://127.0.0.1:{ui_port}/web/"
        server = None
        try:
            # 2. Replay with original timestamps; interrupt collection midway ---------------
            evidence["supervisor_ready_seconds"] = [supervisor.start()]
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tools.opcua.aihub_replay",
                    "server",
                    "--root",
                    str(workspace),
                    "--speed",
                    str(SPEED),
                    "--recorded-timestamps",
                ],
                stdout=(output / "replay.log").open("w"),
                stderr=subprocess.STDOUT,
            )
            replay_began = time.monotonic()
            page.goto(url + "#anomaly")
            record_display(page, "anomaly-freshness")
            shown_text: list[tuple[datetime, str]] = []
            selected = interrupted = False
            while server.poll() is None:
                time.sleep(1.5)
                elapsed = time.monotonic() - replay_began
                if not interrupted and elapsed > 100:
                    evidence["interruption"] = {"stopped_at_replay_seconds": round(elapsed, 1)}
                    evidence["supervisor_stop_seconds"] = supervisor.stop()
                    time.sleep(15)  # the replay keeps publishing while nothing collects
                    evidence["supervisor_ready_seconds"].append(supervisor.start())
                    evidence["interruption"]["restarted_at_replay_seconds"] = round(
                        time.monotonic() - replay_began, 1
                    )
                    interrupted = True
                    shown_text += displayed(page)
                    page.reload()
                    record_display(page, "anomaly-freshness")
                    selected = False
                    continue
                option = page.locator('#anomaly-binding option[value="aihub-1338"]')
                if not selected and option.count():
                    page.select_option("#anomaly-binding", "aihub-1338")
                    selected = True
            evidence["replay_exit"] = server.returncode
            # Let the coordinator close the last window and the runner catch up.
            time.sleep(20)
            shown_text += displayed(page)

            # 3. Exactly-once over every finalized window, latency, gap honesty -------------
            stream = [
                w
                for w in windows.list_windows()
                if (w.source_id, w.asset_id) == (SOURCE_ID, ASSET_ID)
            ]
            results = {r.input_reference["window_id"]: r for r in store.list_results("aihub-1338")}
            checks.add(
                "every-finalized-window-has-one-result",
                {w.window_id for w in stream} == set(results)
                and len(results) == len(store.list_results("aihub-1338")),
                {"windows": len(stream), "results": len(results)},
            )
            latency = [
                (results[w.window_id].processed_at - w.finalized_at).total_seconds()
                for w in stream
                if w.window_id in results
            ]
            evidence["window_finalized_to_commit_seconds"] = percentiles(latency)
            p95 = evidence["window_finalized_to_commit_seconds"]["p95"]
            checks.add(
                "window-finalized-to-commit-p95-le-10s", p95 is not None and p95 <= 10.0, p95
            )
            # The window screen shows "최신 분석 <event start> · 처리 <processed time>" for the
            # latest analyzed window, so a commit is reflected once that start reaches it.
            shown = [
                (at, datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC))
                for at, text in shown_text
                if (match := re.search(r"최신 분석 (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC", text))
            ]
            measured = [
                (r.event_start.astimezone(UTC).replace(microsecond=0), r.processed_at)
                for r in results.values()
                if r.state is StepState.ANALYZED and r.event_start is not None
            ]
            screen_latency, unreflected = reflection_latency(measured, shown)
            evidence["commit_to_screen_seconds"] = {
                **percentiles(screen_latency),
                "unreflected": unreflected,
                "screen_poll_ms": 3000,
            }
            checks.add("every-analyzed-window-reflected-on-screen", unreflected == 0, unreflected)
            p95 = evidence["commit_to_screen_seconds"]["p95"]
            checks.add("commit-to-screen-p95-le-5s", p95 is not None and p95 <= 5.0, p95)
            analyzed = [r for r in results.values() if r.state is StepState.ANALYZED]
            skipped = [r for r in results.values() if r.state is not StepState.ANALYZED]
            evidence["windows"] = {
                "analyzed": len(analyzed),
                "skipped": len(skipped),
                "skip_reasons": sorted({(r.reason or "")[:120] for r in skipped}),
                "event_span": [
                    min(w.window_start for w in stream).isoformat() if stream else None,
                    max(w.window_end for w in stream).isoformat() if stream else None,
                ],
                "accepted_events_per_window": sorted(w.accepted_event_count for w in stream),
            }
            expected_windows = int(4 * 60 / 5)
            checks.add(
                "collection-gap-is-not-shown-as-analyzed-data",
                len(analyzed) < expected_windows,
                f"{len(analyzed)} analyzed of {expected_windows} recorded windows; "
                "the rest are absent or skipped with reasons",
            )

            # 4. Real local-main explanation and human review on the screen -----------------
            page.goto(url + "#anomaly")
            page.select_option("#anomaly-binding", "aihub-1338")
            panel = page.locator("#anomaly-explanation")
            expect(panel).to_contain_text("AI 설명과 사람 검토", timeout=15_000)
            panel.get_by_role("button", name="AI 설명 생성").click()
            expect(panel.locator(".phm-ai-text")).not_to_be_empty(timeout=180_000)
            explanation = {
                "text": panel.locator(".phm-ai-text").inner_text(),
                "grounding_warning": panel.locator(".phm-ai-warning").inner_text(),
            }
            evidence["explanation"] = explanation
            checks.add("real-local-main-explanation", bool(explanation["text"].strip()))
            checks.add(
                "explanation-numbers-grounded",
                not explanation["grounding_warning"],
                explanation["grounding_warning"],
            )
            panel.get_by_role("button", name="검토 요청").click()
            expect(panel.locator(".phm-review-history")).to_contain_text("검토 요청됨")
            panel.get_by_label("검토 메모").first.fill("R/S/T 전류와 전압 원본 신호를 함께 확인함")
            panel.get_by_role("button", name="검토 확인").click()
            expect(panel.locator(".phm-review-history")).to_contain_text("검토 확인됨")
            panel.get_by_role("button", name="검토 종료").click()
            expect(panel.locator(".phm-review-history")).to_contain_text("정비 완료 아님")
            page.screenshot(path=str(output / "anomaly-reviewed.png"), full_page=True)
            page.goto(url + "#rul")
            expect(page.locator("#rul-state")).to_contain_text(
                "근거가 없는 설비에는 표시하지 않습니다", timeout=15_000
            )
            checks.add(
                "rul-screen-states-no-lifecycle-evidence",
                True,
                page.locator("#rul-state").inner_text(),
            )

            # 5. Restart: results, explanation, review persist --------------------------------
            before = len(store.list_results("aihub-1338"))
            supervisor.stop()
            evidence["supervisor_ready_seconds"].append(supervisor.start())
            time.sleep(3)
            checks.add(
                "restart-keeps-results-unchanged",
                len(store.list_results("aihub-1338")) == before,
                before,
            )
            page.goto(url + "#anomaly")
            page.select_option("#anomaly-binding", "aihub-1338")
            panel = page.locator("#anomaly-explanation")
            expect(panel.locator(".phm-ai-text")).to_have_text(explanation["text"], timeout=15_000)
            expect(panel.locator(".phm-review-history")).to_contain_text("정비 완료 아님")
            checks.add("restart-keeps-explanation-and-review", True)
            page.screenshot(path=str(output / "anomaly-after-restart.png"), full_page=True)
            checks.add("no-browser-errors", not errors, errors)
        finally:
            browser.close()
            if server is not None and server.poll() is None:
                server.terminate()
            if supervisor.process is not None and supervisor.process.poll() is None:
                supervisor.stop()

    evidence["checks"] = checks.items
    evidence["pass"] = checks.passed
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    write_evidence(output / "evidence.json", evidence)
    print("VERDICT", "PASS" if checks.passed else "FAIL")
    return 0 if checks.passed else 1


if __name__ == "__main__":
    sys.exit(main())
