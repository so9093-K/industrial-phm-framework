"""Protect the CI event rules for Web read-model and browser contracts.

Without this test, a Python-only monitor DTO change can pass source checks without
starting the HTTP/Chromium runs needed to detect a broken production Web.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/web-next-spike.yml",
    ".github/workflows/forecast-acceptance.yml",
)
WEB_INPUTS = (
    "src/industrial_phm/runtime/operations_web_read.py",
    "src/industrial_phm/runtime/operations_web_phm_models.py",
    "src/industrial_phm/runtime/operations_web_http.py",
    "src/industrial_phm/runtime/operations_web_outlook.py",
    "frontend/src/App.svelte",
    "tests/acceptance/test_operations_web_next_review_browser.py",
)
FORECAST_INPUTS = (
    "src/industrial_phm/runtime/operations_web_read.py",
    "src/industrial_phm/runtime/operations_web_phm_models.py",
    "src/industrial_phm/runtime/operations_web_outlook.py",
    "frontend/src/components/ProjectionExplorer.svelte",
    "tests/acceptance/test_operations_web_next_projection_browser.py",
)


def _paths(path: str, event: str) -> tuple[str, ...]:
    """Read the flat, quoted path-list contract used in these two workflows."""
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    event_header = f"  {event}:"
    assert event_header in lines
    start = lines.index(event_header)
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index] and not
         lines[index].startswith("  ")),
        len(lines),
    )
    block = lines[start:end]
    assert "    paths:" in block
    paths = [
        line.removeprefix('      - "').removesuffix('"')
        for line in block
        if line.startswith('      - "')
    ]
    assert paths, f"{event} must select Web regression paths"
    assert len(paths) == len(set(paths)), "duplicate path globs obscure their ownership"
    return tuple(paths)


def test_web_read_contract_changes_trigger_both_events_and_web_acceptance() -> None:
    for workflow in WORKFLOWS:
        pull = _paths(workflow, "pull_request")
        push = _paths(workflow, "push")
        assert pull == push, f"{workflow} checks PR and main with different input sets"
        changed = WEB_INPUTS if "web-next" in workflow else FORECAST_INPUTS
        for path in changed:
            assert any(fnmatch.fnmatchcase(path, pattern) for pattern in pull), (
                f"{workflow} does not run for changed Web DTO: {path}"
            )
