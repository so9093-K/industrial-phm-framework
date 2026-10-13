"""Continuous Monitor acceptance with original XJTU/AI-Hub replay and fixed packages.

The page stays on #monitor before delivery. Analysis pause, refused input, node outage,
restart, exact result handoff and three viewports are exercised on one supervised node.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
from industrial_phm.application import CollectionDesiredState
from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.demo.aihub_replay import (
    ReplaySelection,
    build_replay_manifest,
    register_replay_source,
    write_replay_manifest,
)
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from tools.phm.acceptance_common import (
    Checks,
    Supervisor,
    cli,
    free_port,
    percentiles,
    set_config,
    write_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--xjtu-workspace", type=Path, required=True)
    parser.add_argument("--aihub-workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("use a new output directory; existing evidence is not overwritten")
    output.mkdir(parents=True)
    workspace = OperationsWorkspace(output / "ws")
    initialize_operations_workspace(workspace)
    port = free_port()
    set_config(workspace.root, "ui", "port", str(port))
    set_config(workspace.root, "collection", "window_duration_seconds", "300.0")
    for previous in (args.xjtu_workspace, args.aihub_workspace):
        store = SqlitePhmAnalysisStore(previous / "phm-analysis.sqlite")
        for binding in store.list_bindings():
            if binding.asset_id not in ("Bearing1_1", "aihub-air-compressor-1338"):
                continue
            source = previous / "models" / binding.package_id
            target = workspace.models_path / binding.package_id
            if not target.exists():
                shutil.copytree(source, target)
            cli(
                "operations",
                "phm",
                "bind",
                str(workspace.root),
                "--package",
                binding.package_id,
                "--source-id",
                binding.source_id,
                "--asset-id",
                binding.asset_id,
                "--binding-id",
                binding.binding_id,
                "--recorded-replay",
            )
    selection = ReplaySelection(
        archive=args.archive,
        member="3.공기압축기/SourceData_16.json",
        binding=PowerHistoryBinding(
            **json.loads(
                Path("tools/opcua/presets/aihub-air-compressor-1338-replay.json").read_text()
            )
        ),
        start_local=datetime.fromisoformat("2020-11-13T13:35:00"),
        end_local=datetime.fromisoformat("2020-11-13T14:15:00"),
    )
    manifest = build_replay_manifest(f"opc.tcp://127.0.0.1:{free_port()}/phm/", selection)
    register_replay_source(
        workspace.root,
        selection,
        manifest,
        name="Recorded compressor 1338",
        desired_state=CollectionDesiredState.STOPPED,
        registered_at=datetime.fromisoformat(str(manifest["prepared_at"])),
    )
    write_replay_manifest(workspace.root, manifest)
    cli(
        "internal",
        "request-collection",
        "--workspace",
        str(workspace.root),
        "--source-id",
        "aihub239-replay-air-compressor-1338",
        "--state",
        "running",
    )
    supervisor = Supervisor(workspace.root, output / "supervisor.log")
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    checks = Checks()
    evidence: dict[str, Any] = {
        "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "started_at": datetime.now(UTC).isoformat(),
        "scenario": "continuous-asset-monitor-original-replay",
        "selection": {
            "start_local": "2020-11-13T13:35:00",
            "end_local": "2020-11-13T14:15:00",
            "speed": 20,
        },
        "package_ids": [b.package_id for b in store.list_bindings()],
    }
    replay_server = None
    paused = None

    def replay(start: int, count: int) -> None:
        cli(
            "operations",
            "phm",
            "replay-xjtu",
            str(workspace.root),
            "--source",
            str(args.source),
            "--bearing",
            "Bearing1_1",
            "--source-id",
            "xjtu-sy-replay",
            "--start",
            str(start),
            "--count",
            str(count),
            "--interval-seconds",
            "0.3",
        )

    from playwright.sync_api import expect, sync_playwright

    try:
        supervisor.start()
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                requests: list[tuple[float, str]] = []
                durations: list[float] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("request", lambda r: requests.append((time.monotonic(), r.url)))
                page.on(
                    "requestfinished",
                    lambda r: (
                        durations.append(r.timing["responseEnd"])
                        if "/api/v1/phm/monitor" in r.url
                        else None
                    ),
                )
                url = f"http://127.0.0.1:{port}/web/"
                page.goto(url + "#monitor")
                model = page.locator('.monitor-model[data-binding-id="anomaly-score-Bearing1_1"]')
                lstm = page.locator(
                    '.monitor-model[data-binding-id="lstm-lstm-autoencoder-v1-Bearing1_1"]'
                )
                compressor = page.locator('.monitor-model[data-binding-id="aihub-1338"]')
                expect(model).to_contain_text("확정된 입력 대기", timeout=15_000)
                checks.add(
                    "page-open-before-inputs-two-assets-five-models",
                    page.locator(".monitor-asset").count() == 2
                    and page.locator(".monitor-model").count() == 5,
                )
                replay_server = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "tools.opcua.aihub_replay",
                        "server",
                        "--root",
                        str(workspace.root),
                        "--speed",
                        "20",
                        "--recorded-timestamps",
                    ],
                    stdout=(output / "replay.log").open("w"),
                    stderr=subprocess.STDOUT,
                )
                replay(1, 2)
                expect(lstm).to_contain_text("LSTM 입력 준비", timeout=20_000)
                checks.add("real-lstm-warmup-visible-on-monitor", True, lstm.inner_text())
                replay(3, 6)
                expect(model).to_contain_text("분석 #8", timeout=20_000)
                expect(lstm).to_contain_text("분석 #8", timeout=20_000)
                expect(compressor).to_contain_text("최근 저장된 분석", timeout=45_000)
                checks.add("both-assets-change-without-manual-refresh", True)
                details = json.loads(workspace.supervisor_state_path.read_text())
                paused = next(
                    c["pid"] for c in details["supervisor"]["components"] if c["kind"] == "analysis"
                )
                os.kill(paused, signal.SIGSTOP)
                replay(9, 1)
                expect(model).to_contain_text("새 입력 분석 대기", timeout=15_000)
                expect(model).to_contain_text("이전 마지막 분석")
                page.screenshot(path=str(output / "analysis-pending-1440.png"), full_page=True)
                checks.add("real-analysis-pause-keeps-input-and-last-output-distinct", True)
                os.kill(paused, signal.SIGCONT)
                paused = None
                expect(model).to_contain_text("분석 #9", timeout=20_000)
                repo = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
                snapshot = repo.latest("xjtu-sy-replay", "Bearing1_1")
                assert snapshot is not None
                bad = output / "invalid.csv"
                bad.write_text("damaged test copy, original source untouched")
                repo.record(replace(snapshot, ordinal=10, file_path=bad))
                expect(model).to_contain_text("최근 입력 분석 거부", timeout=20_000)
                expect(model).to_contain_text("이전 마지막 분석")
                checks.add(
                    "real-refused-input-does-not-look-like-new-analysis", True, model.inner_text()
                )
                page.screenshot(path=str(output / "input-refused-1440.png"), full_page=True)
                before = {
                    b.binding_id: store.list_results(b.binding_id) for b in store.list_bindings()
                }
                supervisor.stop()
                expect(page.locator("#phm-monitor-state")).to_contain_text(
                    "PHM 조회 실패", timeout=15_000
                )
                expect(page.locator(".monitor-model")).to_have_count(0)
                checks.add("node-outage-clears-old-results-on-monitor", True)
                page.screenshot(path=str(output / "node-outage-1440.png"), full_page=True)
                replay(11, 8)
                supervisor.start()
                expect(model).to_contain_text("분석 #18", timeout=30_000)
                expect(lstm).to_contain_text("분석 #18", timeout=30_000)
                checks.add("restart-recovers-monitor-and-all-backlogged-model-inputs", True)
                checks.add(
                    "previous-model-results-unchanged",
                    all(
                        all(store.get_result(binding, row.position) == row for row in saved)
                        for binding, saved in before.items()
                    ),
                )
                # Keep monitoring while the real OPC UA selection finishes; record steady requests.
                began = time.monotonic()
                while "replay selection finished" not in (output / "replay.log").read_text():
                    if time.monotonic() - began > 180:
                        raise TimeoutError("recorded replay did not finish")
                    page.wait_for_timeout(1000)
                steady = [(at, request) for at, request in requests if at >= began + 5]
                checks.add(
                    "steady-monitor-never-loads-model-history-or-refits-condition",
                    not any("/phm/series?" in r or "/condition?" in r for _, r in steady),
                )
                checks.add(
                    "steady-monitor-three-requests-per-poll",
                    all(
                        sum(1 for t, r in steady if at <= t < at + 3 and "/api/v1/" in r) <= 3
                        for at, _ in steady
                    ),
                )
                evidence["steady_requests"] = [
                    {"seconds": round(at - began, 3), "path": r.split(str(port), 1)[-1]}
                    for at, r in steady
                ]
                evidence["phm_overview_http_ms"] = percentiles(durations)
                for width, height in ((1440, 900), (1024, 900), (390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    checks.add(
                        f"monitor-{width}-no-document-overflow",
                        page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                    )
                    page.screenshot(path=str(output / f"monitor-{width}.png"), full_page=True)
                model.get_by_role("link", name="이 시점의 추세·원본 입력 보기").click()
                expect(page.locator("#anomaly-binding")).to_have_value("anomaly-score-Bearing1_1")
                expect(page.locator("#anomaly-detail h3")).to_contain_text("획득 #18")
                expect(page.locator("#anomaly-detail .phm-wave")).to_have_count(2)
                page.reload()
                expect(page.locator("#anomaly-detail h3")).to_contain_text("획득 #18")
                checks.add(
                    "monitor-handoff-preserves-exact-model-position-waveform-after-reload", True
                )
                checks.add("no-browser-page-errors", not errors, errors)
            finally:
                browser.close()
    except Exception as exc:
        checks.add("continuous-monitor-journey-completed", False, str(exc))
    finally:
        if paused:
            os.kill(paused, signal.SIGCONT)
        if replay_server and replay_server.poll() is None:
            replay_server.terminate()
            replay_server.wait(timeout=15)
        if supervisor.process and supervisor.process.poll() is None:
            supervisor.stop()
        evidence.update(
            checks=checks.items, passed=checks.passed, finished_at=datetime.now(UTC).isoformat()
        )
        write_evidence(output / "evidence.json", evidence)
    return 0 if checks.passed else 1


if __name__ == "__main__":
    sys.exit(main())
