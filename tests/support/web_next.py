"""Shared Web-next navigation checks for Chromium acceptance tests."""

from __future__ import annotations

from typing import Any


def expect_place(pw: Any, page: Any, tab: str, method: str | None = None) -> None:
    """The asset screen shows the expected task tab (and analysis method) as current."""
    tabs = page.get_by_role("navigation", name="설비 화면")
    pw.expect(tabs.get_by_role("link", name=tab, exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    if method is not None:
        methods = page.get_by_role("navigation", name="분석 방법")
        pw.expect(methods.get_by_role("link", name=method, exact=True)).to_have_attribute(
            "aria-current", "true"
        )


def choose_asset(page: Any, asset_id: str) -> None:
    """Switch to another asset from the asset screen header."""
    page.get_by_label("다른 설비").select_option(asset_id)
