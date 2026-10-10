"""Bounded, supervisor-owned synthetic first-run demo actions for the local Web.

The demo is a separate loopback service and sibling workspace; neither its data
nor its lifecycle is merged into the real Operations workspace. These actions
are never authorized on the standalone Web read/preview server.
"""

from __future__ import annotations

from pathlib import Path

from industrial_phm.runtime.operations_sample import (
    current_first_run_sample,
    launch_first_run_sample,
    stop_first_run_sample,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def execute_web_sample_action(root: Path, route: str, payload: dict[str, object]) -> dict[str, object]:
    """Run only fixed, empty-payload sample actions in the supervisor process."""
    if payload:
        raise ValueError("synthetic sample actions do not accept user-supplied paths or ports")
    if route == "/api/v1/demo/synthetic/start":
        launch = launch_first_run_sample(OperationsWorkspace(root))
        return {
            "schema_version": 1,
            "state": "running",
            "synthetic": True,
            "url": launch.url,
            "separate_workspace": True,
        }
    if route == "/api/v1/demo/synthetic/stop":
        stop_first_run_sample()
        return {"schema_version": 1, "state": "stopped", "synthetic": True}
    if route == "/api/v1/demo/synthetic/status":
        launch = current_first_run_sample()
        if launch is None:
            return {"schema_version": 1, "state": "stopped", "synthetic": True}
        return {
            "schema_version": 1,
            "state": "running",
            "synthetic": True,
            "url": launch.url,
            "separate_workspace": True,
        }
    raise ValueError("unknown synthetic sample action")
