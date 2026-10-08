"""Chromium acceptance for the real first-run Operations entry and recovery boundary.

This is intentionally a real `operations up` process + browser test, not marimo
script-mode composition. A locally generated OPC UA mapping is registered without
claiming device receipt: the Monitor handoff must remain gated.

Run explicitly with the Operations extra and Playwright's Chromium installed.
The ordinary base pytest suite skips this test when Playwright is unavailable.
"""

from __future__ import annotations

import json
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
from industrial_phm.presentation.operations_locale import operations_page_label, operations_text
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
    width = page.viewport_size["width"]
    page.screenshot(path=str(target / f"{locale}-{width}-{stage}.png"), full_page=True)


def _check_browser_layout(page, *, locale: str, stage: str, tmp_path: Path) -> None:
    """Reject document-level horizontal clipping at both supported widths."""

    metrics = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
        })"""
    )
    if metrics["documentWidth"] > metrics["viewport"] + 2:
        _screenshot(page, locale=locale, stage=f"{stage}-overflow", tmp_path=tmp_path)
    assert metrics["documentWidth"] <= metrics["viewport"] + 2, (
        f"{locale} {stage}: unintended horizontal overflow: {metrics}"
    )


def _capture_setup_accessibility(page, *, locale: str, tmp_path: Path) -> None:
    """Preserve marimo control/label semantics for tracked accessibility issue #444."""

    fields = {}
    for key in ("setup.source_id", "setup.name", "common.asset", "setup.endpoint"):
        label = operations_text(key, locale)
        visible_label = page.get_by_text(label, exact=True).last
        visible_label.wait_for(state="visible", timeout=30_000)
        # marimo 0.24.2 renders a visible label without an input id/for link.
        # Matching placeholder supplies Chromium's accessible-name fallback.
        field = page.get_by_role("textbox", name=label, exact=True)
        field.wait_for(state="visible", timeout=30_000)
        fields[key] = {
            "visible_label": visible_label.evaluate("(node) => node.outerHTML.slice(0, 750)"),
            "control": field.evaluate(
                """(node) => ({
                    html: node.outerHTML.slice(0, 900),
                    ariaLabel: node.getAttribute('aria-label'),
                    ariaLabelledby: node.getAttribute('aria-labelledby'),
                    placeholder: node.getAttribute('placeholder'),
                    associatedLabels: [...(node.labels || [])].map(e => e.textContent.trim()),
                })"""
            ),
            "accessible_role_and_name_count": page.get_by_role(
                "textbox", name=label, exact=True
            ).count(),
        }
    target = Path(os.environ.get("PHM_FIRST_RUN_SCREENSHOTS", str(tmp_path / "screenshots")))
    target.mkdir(parents=True, exist_ok=True)
    width = page.viewport_size["width"]
    (target / f"{locale}-{width}-setup-accessibility.json").write_text(
        json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for key, result in fields.items():
        label = operations_text(key, locale)
        assert result["accessible_role_and_name_count"] == 1, (
            f"{locale}: input {key} has no unique accessible name: {result}"
        )
        assert result["control"]["placeholder"] == label, (
            f"{locale}: input {key} has no localized accessible-name fallback: {result}"
        )


def _fill_labeled_field(page, *, label: str, value: str, tag: str = "input") -> None:
    """Find the text input by its visible, programmatically associated label."""
    # The Setup heading may appear before its reactive form controls finish mounting.
    field = page.get_by_role("textbox", name=label, exact=True)
    field.wait_for(state="visible", timeout=30_000)
    assert field.evaluate("(node) => node.tagName.toLowerCase()") == tag
    field.fill(value)


@pytest.mark.parametrize("locale", ["en-US", "ko-KR"])
@pytest.mark.parametrize("viewport_width", [1024, 1440])
def test_first_run_browser_sample_real_and_resume(
    tmp_path: Path, locale: str, viewport_width: int
) -> None:
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
                context = browser.new_context(viewport={"width": viewport_width, "height": 900})
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
                _check_browser_layout(page, locale=locale, stage="fresh", tmp_path=tmp_path)
                _screenshot(page, locale=locale, stage="fresh", tmp_path=tmp_path)

                # Verify keyboard activation, not only pointer-based demo launch.
                sample_start_button = page.get_by_role(
                    "button", name=operations_text("first_run.sample.title", locale)
                )
                sample_start_button.focus()
                expect(sample_start_button).to_be_focused()
                sample_start_button.press("Enter")
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
                    expect(sample.locator(".mw-shell")).to_be_visible(timeout=60_000)
                    # Monitor is a manual snapshot: samples may arrive after
                    # its first render, so explicitly exercise the Refresh action.
                    refresh = sample.get_by_role(
                        "button", name=operations_text("monitor.refresh_aria", locale)
                    )
                    for _ in range(10):
                        if sample.locator(".mw-plot svg").count():
                            break
                        refresh.click(timeout=20_000)
                        expect(sample.locator(".mw-shell.mw-pending")).to_have_count(
                            0, timeout=20_000
                        )
                        sample.wait_for_timeout(3_000)
                    expect(sample.locator(".mw-plot svg")).to_be_visible(timeout=20_000)
                    expect(sample.locator(".mw-plot circle").first).to_be_attached(timeout=20_000)
                except AssertionError as error:
                    _screenshot(sample, locale=locale, stage="sample-failure", tmp_path=tmp_path)
                    sample_body = sample.locator("body").inner_text(timeout=5_000)
                    raise AssertionError(
                        f"sample URL: {sample.url}; title: {sample.title()}; "
                        f"body: {sample_body[:2000]}; "
                        f"browser errors: {errors[-8:]}; "
                        f"sample child log: {_logs(workspace.logs_path / 'first-run-sample.log')}"
                    ) from error
                _check_browser_layout(
                    sample, locale=locale, stage="sample-observations", tmp_path=tmp_path
                )
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
                # Wait for the actual Setup inputs; a route heading can appear
                # before the reactive form settles, especially at 1440 px.
                try:
                    _capture_setup_accessibility(page, locale=locale, tmp_path=tmp_path)
                except Exception:
                    _screenshot(
                        page, locale=locale, stage="real-entry-failure", tmp_path=tmp_path
                    )
                    raise
                _check_browser_layout(page, locale=locale, stage="real-entry", tmp_path=tmp_path)
                _screenshot(page, locale=locale, stage="real-entry", tmp_path=tmp_path)

                # Exercise a real validation error before the successful retry.
                page.get_by_role(
                    "button", name=operations_text("setup.review_save_source", locale)
                ).click()
                recovery_panel = page.locator(".phm-error-content[role='alert']")
                expect(recovery_panel).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                expect(recovery_panel).to_contain_text(
                    operations_text("setup.failure.what", locale)
                )
                expect(recovery_panel).to_contain_text(
                    operations_text("setup.failure.next", locale)
                )
                detail_summary = page.locator(".phm-error-technical summary")
                detail_summary.focus()
                expect(detail_summary).to_be_focused()
                detail_summary.press("Enter")
                expect(page.locator(".phm-error-technical code")).to_be_visible()
                detail_summary.press("Enter")
                expect(page.locator(".phm-error-technical code")).to_be_hidden()
                _check_browser_layout(
                    page, locale=locale, stage="real-validation-error", tmp_path=tmp_path
                )
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()
                _screenshot(page, locale=locale, stage="real-validation-error", tmp_path=tmp_path)

                _fill_labeled_field(
                    page, label=operations_text("setup.source_id", locale), value=source_id
                )
                _fill_labeled_field(
                    page,
                    label=operations_text("setup.name", locale),
                    value="First-run acceptance source",
                )
                _fill_labeled_field(
                    page,
                    label=operations_text("common.asset", locale),
                    value="acceptance-motor-01",
                )
                _fill_labeled_field(
                    page,
                    label=operations_text("setup.endpoint", locale),
                    value="opc.tcp://127.0.0.1:65530",
                )
                page.get_by_text(
                    operations_text("setup.advanced_nodeid_mapping", locale), exact=True
                ).click()
                _fill_labeled_field(
                    page,
                    label=operations_text("setup.advanced_mapping", locale),
                    value="Current_L1,ns=2;s=Current_L1",
                    tag="textarea",
                )
                page.get_by_role(
                    "button", name=operations_text("setup.review_save_source", locale)
                ).click()
                expect(
                    page.get_by_text(
                        operations_text("setup.source_saved", locale).format(source_id=source_id)
                    )
                ).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                expect(recovery_panel).to_have_count(0)
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
                _check_browser_layout(
                    page, locale=locale, stage="real-awaiting-receipt", tmp_path=tmp_path
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
                page = browser.new_page(viewport={"width": viewport_width, "height": 900})
                page.goto(url)
                expect(page.locator(".mw-shell")).to_be_visible(timeout=_BROWSER_TIMEOUT_MS)
                expect(page.locator(".mw-asset h1")).to_contain_text(
                    "acceptance-motor-01", timeout=_BROWSER_TIMEOUT_MS
                )
                assert page.get_by_role("heading", name="Industrial PHM").count() == 0
                _check_browser_layout(
                    page, locale=locale, stage="configured-resume", tmp_path=tmp_path
                )
                _screenshot(page, locale=locale, stage="configured-resume", tmp_path=tmp_path)

                # With an already registered source, every Operations page is
                # reachable through the same keyboard-accessible navigation.
                for destination in (
                    "assets",
                    "investigations",
                    "maintenance",
                    "system",
                    "setup",
                    "monitor",
                ):
                    page_label = operations_page_label(destination, locale)
                    navigation_button = page.locator(".mw-pages").get_by_role(
                        "button", name=page_label, exact=True
                    )
                    navigation_button.focus()
                    expect(navigation_button).to_be_focused()
                    navigation_button.press("Enter")
                    expect(page.locator('.mw-pages button[aria-current="page"]')).to_have_text(
                        page_label, timeout=_BROWSER_TIMEOUT_MS
                    )
                    _check_browser_layout(
                        page, locale=locale, stage=f"nav-{destination}", tmp_path=tmp_path
                    )
                    _screenshot(page, locale=locale, stage=f"nav-{destination}", tmp_path=tmp_path)
            finally:
                browser.close()
    except Exception as error:
        raise AssertionError(
            f"first-run browser acceptance failed for {locale}: {error}\n"
            f"Operations process log:\n{_logs(log_path)}"
        ) from error
    finally:
        _stop_node(process, workspace, log)
