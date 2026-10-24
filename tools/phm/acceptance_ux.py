"""Inspect saved recorded results in the default task-based Operations Web.

Run acceptance_xjtu/acceptance_aihub first to prepare saved inputs and results.
This task-UI check does not replay sources or fit models.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.phm.acceptance_common import Checks, Supervisor, write_evidence
from tools.phm.acceptance_web import open_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scenario", choices=("xjtu", "aihub"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    import tomllib

    from playwright.sync_api import expect, sync_playwright

    from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore

    workspace, output = args.workspace.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = tomllib.loads((workspace / "config.toml").read_text())
    url = f"http://127.0.0.1:{config['ui']['port']}/web/"
    models = [
        item
        for item in SqlitePhmAnalysisStore(workspace / "phm-analysis.sqlite").list_bindings()
        if item.asset_id
        == ("Bearing1_1" if args.scenario == "xjtu" else "aihub-air-compressor-1338")
    ]
    checks = Checks()
    evidence: dict[str, Any] = {
        "protocol": "operations-web-task-ui-v1",
        "scenario": args.scenario,
        "started_at": datetime.now(UTC).isoformat(),
        "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "viewports": [],
    }
    supervisor = Supervisor(workspace, output / "supervisor.log")
    try:
        supervisor.start()
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                evidence["browser"] = {"name": "Chromium", "version": browser.version}
                for width in (390, 1024, 1440):
                    for model in models:
                        page = browser.new_page(
                            viewport={"width": width, "height": 900}, locale="ko-KR"
                        )
                        errors = []
                        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
                        open_model(page, url, model.binding_id)
                        selector = page.get_by_label("측정 선택 (최근 64회)")
                        expect(selector).to_be_visible(timeout=30_000)
                        selected = selector.input_value()
                        expect(page.locator("[data-model-position]")).to_be_visible()
                        expect(page.get_by_role("table", name="측정 특징 비교")).to_be_visible()
                        selector.focus()
                        page.keyboard.press("Tab")
                        checks.add(
                            f"keyboard-focus-{width}-{model.binding_id}",
                            page.evaluate("document.activeElement !== document.body"),
                        )
                        page.reload()
                        expect(selector).to_have_value(selected)
                        checks.add(f"bookmark-{width}-{model.binding_id}", True, selected)
                        checks.add(
                            f"no-overflow-{width}-{model.binding_id}",
                            page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"),
                        )
                        checks.add(f"no-page-errors-{width}-{model.binding_id}", not errors, errors)
                        page.screenshot(
                            path=str(output / f"{model.binding_id}-{width}.png"), full_page=True
                        )
                        evidence["viewports"].append(
                            {
                                "width": width,
                                "binding": model.binding_id,
                                "position": selected,
                                "raw_figures": page.locator("section.input figure").count(),
                            }
                        )
                        page.close()
                checks.add("recorded-models-inspected", bool(models), len(models))
            finally:
                browser.close()
    except Exception as error:
        checks.add("task-ui-inspection-completed", False, str(error))
    finally:
        if supervisor.process is not None and supervisor.process.poll() is None:
            supervisor.stop()
        evidence.update(
            checks=checks.items, passed=checks.passed, finished_at=datetime.now(UTC).isoformat()
        )
        write_evidence(output / "evidence.json", evidence)
    return 0 if checks.passed else 1


if __name__ == "__main__":
    sys.exit(main())
