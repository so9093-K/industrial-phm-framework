"""Repository-wide test policy shared by every test layer."""

from __future__ import annotations

import sys

import pytest


def pytest_runtest_setup(item: pytest.Item) -> None:
    # Operations supervises its Web commands with Linux-only peer credentials and pidfd.
    # Elsewhere these tests report an explicit skip instead of an unrelated-looking failure.
    if item.get_closest_marker("linux_only") is not None and sys.platform != "linux":
        pytest.skip("Linux 전용(SO_PEERCRED·pidfd): make verify-linux로 실행하세요")
