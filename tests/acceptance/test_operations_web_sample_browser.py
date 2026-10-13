"""Actual local Web → supervisor IPC → isolated synthetic demo process journey."""

from __future__ import annotations

import socket
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from industrial_phm.runtime import (
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from tests.acceptance.test_operations_web_controlled_journey_browser import _port, _start, _stop


def test_supervised_web_launches_and_stops_real_isolated_synthetic_demo(tmp_path: Path) -> None:
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux supervisor peer credentials required")
    playwright = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("asyncua")

    root = OperationsWorkspace(tmp_path / "real-operations")
    initialized = initialize_operations_workspace(root)
    port = _port()
    write_operations_runtime_config(
        root.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    original_config = root.config_path.read_bytes()
    log = tmp_path / "supervisor-sample.log"
    proc = _start(root.root, port, log)
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 900})
                page.on("dialog", lambda dialog: dialog.accept())
                page.goto(f"http://127.0.0.1:{port}/web/#connect", wait_until="domcontentloaded")
                page.locator("#connection-progress").evaluate("el => el.open = true")
                playwright.expect(page.locator("#sample-start")).to_be_enabled(timeout=30000)
                playwright.expect(page.locator("#sample-stop")).to_be_disabled()
                playwright.expect(page.locator("#sample-open")).to_be_hidden()
                page.get_by_role("button", name="격리 샘플 시작").click()
                playwright.expect(page.locator("#sample-open")).to_be_visible(timeout=45000)
                link = page.locator("#sample-open")
                url = link.get_attribute("href")
                assert url is not None and url.startswith("http://127.0.0.1:")
                assert link.get_attribute("rel") == "noopener noreferrer"
                assert link.get_attribute("target") == "_blank"
                parsed = urlsplit(url)
                assert parsed.hostname == "127.0.0.1"
                assert parsed.port is not None and parsed.port != port
                assert parsed.path == "/web/"
                assert not parsed.query and not parsed.fragment
                connection = HTTPConnection("127.0.0.1", parsed.port, timeout=5)
                try:
                    connection.request("GET", parsed.path)
                    response = connection.getresponse()
                    assert response.status == 200
                    assert b'id="sample-start"' in response.read()
                finally:
                    connection.close()
                with page.expect_popup() as sample_popup:
                    link.click()
                sample_page = sample_popup.value
                sample_page.wait_for_load_state("domcontentloaded")
                assert sample_page.url == url
                sample_page.locator('nav a[href="#connect"]').click()
                playwright.expect(sample_page.locator(".synthetic-context")).to_be_visible(
                    timeout=30000
                )
                sample_page.close()

                samples = list(tmp_path.glob("demo-synthetic-*"))
                assert len(samples) == 1
                assert samples[0] != root.root
                assert (samples[0] / "config.toml").exists()
                assert not root.source_registry_path.exists()
                assert root.config_path.read_bytes() == original_config

                # The existing sample remains a separate application after reloading Web.
                page.reload(wait_until="domcontentloaded")
                page.locator("#connection-progress > summary").click()
                playwright.expect(page.locator("#sample-open")).to_be_visible(timeout=15000)
                assert page.locator("#sample-open").get_attribute("href") == url
                page.set_viewport_size({"width": 1440, "height": 900})
                assert page.evaluate(
                    "() => document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                page.get_by_role("button", name="격리 샘플 종료").click()
                playwright.expect(page.locator("#sample-stop")).to_be_disabled(timeout=45000)
                playwright.expect(page.locator("#sample-start")).to_be_enabled()
                playwright.expect(page.locator("#sample-open")).to_be_hidden()
                page.get_by_role("button", name="샘플 상태 다시 확인").click()
                playwright.expect(page.locator("#sample-status")).to_contain_text(
                    "격리 샘플이 실행 중이지 않습니다"
                )
                assert not root.source_registry_path.exists()
                assert root.config_path.read_bytes() == original_config
            finally:
                browser.close()
    finally:
        _stop(proc, root.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
