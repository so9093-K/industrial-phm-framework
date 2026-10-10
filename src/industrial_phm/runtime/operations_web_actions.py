"""Execute only the bounded Operations Web source-action allowlist.

The caller must authorize and serialize mutations before entering this dispatcher.
This boundary is shared by the standalone preview writer and a future
supervisor-owned command broker; it grants no write authority by itself.
"""

from __future__ import annotations

from pathlib import Path

from industrial_phm.runtime.operations_web_opcua import (
    browse_local_opcua,
    diagnose_local_opcua,
    register_local_opcua,
)
from industrial_phm.runtime.operations_web_review import (
    record_web_review_action,
    request_web_analysis_review,
)
from industrial_phm.runtime.operations_web_sample import execute_web_sample_action
from industrial_phm.runtime.operations_web_setup import (
    backfill_workspace_file_history,
    change_web_source_control,
    receive_workspace_file_source,
    register_workspace_csv_source,
)

WEB_SOURCE_ACTION_ROUTES: frozenset[str] = frozenset(
    {
        "/api/v1/sources/file",
        "/api/v1/sources/file/receive",
        "/api/v1/sources/file/backfill",
        "/api/v1/sources/lifecycle",
        "/api/v1/sources/collection",
        "/api/v1/sources/opcua/browse",
        "/api/v1/sources/opcua",
        "/api/v1/sources/opcua/diagnose",
        "/api/v1/reviews/request",
        "/api/v1/reviews/action",
        "/api/v1/demo/synthetic/start",
        "/api/v1/demo/synthetic/stop",
        "/api/v1/demo/synthetic/status",
    }
)

# These may spawn or stop an entire process tree. The standalone Web
# preview must never acquire this capability through its local writer path.
WEB_SUPERVISOR_ONLY_ACTION_ROUTES = frozenset(
    {
        "/api/v1/demo/synthetic/start",
        "/api/v1/demo/synthetic/stop",
        "/api/v1/demo/synthetic/status",
    }
)


def execute_web_source_action(
    root: Path, route: str, payload: dict[str, object]
) -> dict[str, object]:
    """Dispatch an explicitly authorized command through existing action facades."""
    if route not in WEB_SOURCE_ACTION_ROUTES:
        raise ValueError("unknown Web source action")
    if route in WEB_SUPERVISOR_ONLY_ACTION_ROUTES:
        return execute_web_sample_action(root, route, payload)
    if route == "/api/v1/sources/file":
        return register_workspace_csv_source(root, payload)
    if route == "/api/v1/sources/file/receive":
        return receive_workspace_file_source(root, payload)
    if route == "/api/v1/sources/file/backfill":
        return backfill_workspace_file_history(root, payload)
    if route == "/api/v1/sources/opcua/browse":
        return browse_local_opcua(root, payload)
    if route == "/api/v1/sources/opcua":
        return register_local_opcua(root, payload)
    if route == "/api/v1/sources/opcua/diagnose":
        return diagnose_local_opcua(root, payload)
    if route == "/api/v1/sources/lifecycle":
        return change_web_source_control(root, "lifecycle", payload)
    if route == "/api/v1/sources/collection":
        return change_web_source_control(root, "collection", payload)
    if route == "/api/v1/reviews/request":
        return request_web_analysis_review(root, payload)
    return record_web_review_action(root, payload)
