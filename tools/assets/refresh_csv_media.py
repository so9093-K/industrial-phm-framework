"""Re-capture the real CSV onboarding journey in a disposable writable Web workspace.

No personal files, existing Operations workspaces, field equipment, AI endpoint, or
model training are used. Actual file validation, backfill, analysis, forecast and review
actions run through the application.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from tests.support.web_next import start_web, stop_web
from tools.assets.capture_usecases import ROOT, VIEWPORT, capture_csv
from tools.assets.pump_csv import write


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="phm-csv-media-") as temporary:
        root = Path(temporary)
        workspace = OperationsWorkspace(root / "workspace")
        initialize_operations_workspace(workspace)
        source = root / "cooling-pump.csv"
        write(source)
        server, thread = start_web(workspace.root, writer=True)
        try:
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch()
                page = browser.new_page(viewport=VIEWPORT, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    output = ROOT / "assets/csv"
                    output.mkdir(parents=True, exist_ok=True)
                    capture_csv(page, f"http://127.0.0.1:{server.server_port}", output, source)
                    assert not errors, errors
                finally:
                    browser.close()
        finally:
            stop_web(server, thread)


if __name__ == "__main__":
    main()
