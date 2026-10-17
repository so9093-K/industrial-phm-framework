"""Real supervised Web → isolated synthetic workspace → reload → stop."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.application import JsonSourceRepository
from industrial_phm.runtime import (
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from tests.acceptance.test_operations_web_controlled_journey_browser import _port, _start, _stop

pytestmark = pytest.mark.linux_only


def test_supervised_sample_is_separate_read_only_and_stoppable(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "parent")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    original = workspace.config_path.read_bytes()
    log = tmp_path / "supervisor.log"
    proc = _start(workspace.root, port, log)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                page.goto(f"http://127.0.0.1:{port}/web/?page=system")
                sample = page.get_by_role("region", name="예시로 둘러보기")
                sample.get_by_role("button", name="예시 시작").click()
                link = sample.get_by_role("link", name="예시 화면 열기 (새 탭)")
                pw.expect(link).to_be_visible(timeout=60_000)
                href = link.get_attribute("href")
                assert href and not href.startswith(f"http://127.0.0.1:{port}/")
                with page.expect_popup() as popup:
                    link.click()
                example = popup.value
                pw.expect(
                    example.get_by_text("합성 예시 데이터 · 별도 작업공간 · 보기 전용")
                ).to_be_visible(timeout=30_000)
                pw.expect(example.locator("a.row").first).to_be_visible(timeout=30_000)
                session = example.request.get(
                    example.url.split("/web/")[0] + "/api/v1/session"
                ).json()
                assert session["write_scope"] == "read-only-synthetic-demo"
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()
                assert workspace.config_path.read_bytes() == original
                example.get_by_role("link", name="내 작업공간으로 돌아가기").click()
                pw.expect(example.get_by_role("heading", name="운영 관리", level=1)).to_be_visible()
                page.reload()
                pw.expect(link).to_have_attribute("href", href)
                sample.get_by_role("button", name="예시 종료").click()
                sample.get_by_role("button", name="종료하기").click()
                pw.expect(sample.get_by_role("button", name="예시 시작")).to_be_visible(
                    timeout=45_000
                )
                assert not JsonSourceRepository(workspace.source_registry_path).list_sources()
            finally:
                browser.close()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text()[-4000:]
