"""Chromium acceptance for the real first-run Operations entry and recovery boundary.

This is intentionally a real `operations up` process + browser test, not marimo
script-mode composition. A locally generated OPC UA mapping is registered without
claiming device receipt: the Monitor handoff must remain gated.

Run explicitly with the Operations extra and Playwright's Chromium installed.
The ordinary base pytest suite skips this test when Playwright is unavailable.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import BinaryIO

import pytest

pytest.importorskip("asyncua")
pytest.importorskip("duckdb")
pytest.importorskip("marimo")

from industrial_phm.application import JsonSourceRepository
from industrial_phm.presentation.operations_locale import operations_text
from industrial_phm.runtime import (
    OperationsRuntimeConfig,
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config

_CLI_BOOTSTRAP = "from industrial_phm.cli import main; raise SystemExit(main())"
_BROWSER_TIMEOUT_MS = 60_000


def _cli(*parts: str) -> list[str]:
    return [sys.executable, "-c", _CLI_BOOTSTRAP, *parts]


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _logs(path: Path) -> str:
    if not path.is_file():
        return "<log unavailable>"
    return path.read_text(encoding="utf-8", errors="replace")[-12_000:]


def _start_node(
    workspace: OperationsWorkspace,
    *,
    port: int,
    locale: str,
    log_path: Path,
) -> tuple[subprocess.Popen[bytes], BinaryIO]:
    initialize_operations_workspace(workspace)
    write_operations_runtime_config(
        workspace.config_path,
        OperationsRuntimeConfig(ui=OperationsUiConfig(port=port)),
    )
    log = log_path.open("ab", buffering=0)
    environment = {**os.environ, "INDUSTRIAL_PHM_LOCALE": locale}
    process = subprocess.Popen(
        _cli("operations", "up", str(workspace.root)),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=environment,
    )
    deadline = time.monotonic() + 60.0
    url = f"http://127.0.0.1:{port}"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log.close()
            raise AssertionError(
                f"Operations exited before first-run UI: code={process.returncode}\n"
                f"{_logs(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return process, log
        except OSError:
            pass
        time.sleep(0.25)
    _stop_node(process, workspace, log)
    raise AssertionError(f"Operations UI did not start at {url}\n{_logs(log_path)}")


def _stop_node(
    process: subprocess.Popen[bytes],
    workspace: OperationsWorkspace,
    log: BinaryIO,
) -> None:
    try:
        if process.poll() is None:
            subprocess.run(
                _cli("operations", "stop", str(workspace.root)),
                capture_output=True,
                check=False,
                timeout=15,
            )
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        log.close()


def _wait_port_closed(port: int, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                pass
        except OSError:
            return
        time.sleep(0.1)
    raise AssertionError(f"sample child still listening on loopback port {port}")


def _screenshot(page, *, locale: str, stage: str, tmp_path: Path) -> None:
    target = Path(os.environ.get("PHM_FIRST_RUN_SCREENSHOTS", str(tmp_path / "screenshots")))
    target.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target / f"{locale}-{stage}.png"), full_page=True)


@pytest.mark.parametrize("locale", ["en-US", "ko-KR"])
def test_first_run_browser_sample_real_and_resume(tmp_path: Path, locale: str) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    expect = playwright.expect
    workspace = OperationsWorkspace(tmp_path / "real-operations")
    port = _free_port()
    log_path = tmp_path / "operations-process.log"
    process, log = _start_node(workspace, port=port, locale=locale, log_path=log_path)
    url = f"http://127.0.0.1:{port}"
    source_id = "acceptance-opc-source"

    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                context = browser.new_context(viewport={"width": 1024, "height": 900})
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.get_by_role("heading", name="Industrial PHM")).to_be_visible(
                    timeout=_BROWSER_TIMEOUT_MS
                )
                expect(
                    page.get_by_role(
                        "button", name=operations_text("first_run.sample.title", locale)
                    )
                ).to_be_visible()
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()
                _screenshot(page, locale=locale, stage="fresh", tmp_path=tmp_path)

                # A browser click starts the existing packaged demo in an isolated workspace.
                page.get_by_role(
                    "button", name=operations_text("first_run.sample.title", locale)
                ).click()
                expect(
                    page.get_by_role(
                        "heading", name=operations_text("first_run.sample.ready", locale)
                    )
                ).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                sample_link = page.get_by_role(
                    "link", name=operations_text("first_run.sample.open", locale)
                )
                sample_url = sample_link.get_attribute("href")
                assert sample_url is not None and sample_url.startswith("http://127.0.0.1:")
                sample_port = int(sample_url.rsplit(":", 1)[1])
                assert sample_port != port

                with context.expect_page() as popup_info:
                    sample_link.click()
                sample = popup_info.value
                sample.on("pageerror", lambda error: errors.append(str(error)))
                sample.wait_for_load_state("domcontentloaded", timeout=30_000)
                try:
                    expect(sample.locator(".mw-plot svg")).to_be_visible(timeout=40_000)
                    expect(sample.locator(".mw-plot circle").first).to_be_attached(timeout=40_000)
                except AssertionError as error:
                    _screenshot(sample, locale=locale, stage="sample-failure", tmp_path=tmp_path)
                    sample_body = sample.locator("body").inner_text(timeout=5_000)
                    raise AssertionError(
                        f"sample URL: {sample.url}; title: {sample.title()}; "
                        f"body: {sample_body[:2000]}; "
                        f"sample child log: {_logs(workspace.logs_path / 'first-run-sample.log')}"
                    ) from error
                _screenshot(sample, locale=locale, stage="sample-observations", tmp_path=tmp_path)
                sample.close()

                # Closing the sample must stop the child without contaminating real data.
                page.get_by_role(
                    "button", name=operations_text("first_run.sample.stop", locale)
                ).click()
                expect(page.get_by_role("heading", name="Industrial PHM")).to_be_visible(
                    timeout=_BROWSER_TIMEOUT_MS
                )
                _wait_port_closed(sample_port)
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()

                # Real data is a distinct guided path. A source registration is not receipt.
                page.get_by_role(
                    "button", name=operations_text("first_run.real.open", locale)
                ).click()
                expect(
                    page.get_by_role("heading", name=operations_text("setup.title", locale))
                ).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                _screenshot(page, locale=locale, stage="real-entry", tmp_path=tmp_path)
                source_field = page.get_by_role(
                    "textbox", name=operations_text("setup.source_id", locale)
                )
                try:
                    expect(source_field).to_be_visible(timeout=10_000)
                except AssertionError as error:
                    inputs = page.locator("input, textarea").evaluate_all(
                        "(nodes) => nodes.map(n => n.outerHTML.slice(0, 400))"
                    )
                    raise AssertionError(
                        f"Setup source ID is not accessible; locale={locale}; "
                        f"body={page.locator('body').inner_text()[:3500]}; "
                        f"inputs={inputs}"
                    ) from error
                source_field.fill(source_id)
                page.get_by_role("textbox", name=operations_text("setup.name", locale)).fill(
                    "First-run acceptance source"
                )
                page.get_by_role("textbox", name=operations_text("common.asset", locale)).fill(
                    "acceptance-motor-01"
                )
                page.get_by_role("textbox", name=operations_text("setup.endpoint", locale)).fill(
                    "opc.tcp://127.0.0.1:65530"
                )
                page.get_by_text(
                    operations_text("setup.advanced_nodeid_mapping", locale), exact=True
                ).click()
                page.get_by_role(
                    "textbox", name=operations_text("setup.advanced_mapping", locale)
                ).fill("Current_L1,ns=2;s=Current_L1")
                page.get_by_role(
                    "button", name=operations_text("setup.review_save_source", locale)
                ).click()
                expect(
                    page.get_by_text(
                        operations_text("setup.source_saved", locale).format(source_id=source_id)
                    )
                ).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                assert tuple(
                    item.source_id
                    for item in JsonSourceRepository(workspace.source_registry_path).list_sources()
                ) == (source_id,)
                expect(
                    page.get_by_text(operations_text("setup.monitor_locked", locale))
                ).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                assert (
                    page.get_by_role(
                        "button", name=operations_text("setup.open_monitor", locale)
                    ).count()
                    == 0
                )
                _screenshot(page, locale=locale, stage="real-awaiting-receipt", tmp_path=tmp_path)
                assert not errors, errors
            finally:
                browser.close()

        # A new UI process/session must bypass landing for the configured workspace.
        _stop_node(process, workspace, log)
        process, log = _start_node(workspace, port=port, locale=locale, log_path=log_path)
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 900})
                page.goto(url)
                expect(page.locator(".mw-shell")).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                expect(page.locator(".mw-asset h1")).to_contain_text(
                    "acceptance-motor-01", timeout=_BROWSER_TIMEOUT_MS
                )
                assert page.get_by_role("heading", name="Industrial PHM").count() == 0
                _screenshot(page, locale=locale, stage="configured-resume", tmp_path=tmp_path)
            finally:
                browser.close()
    except Exception as error:
        raise AssertionError(
            f"first-run browser acceptance failed for {locale}: {error}\n"
            f"Operations process log:\n{_logs(log_path)}"
        ) from error
    finally:
        _stop_node(process, workspace, log)
