"""Fail-closed Web action dispatch contract for a future supervisor-owned writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from industrial_phm.runtime import operations_web_actions as actions


@pytest.mark.parametrize(
    ("route", "handler", "kind"),
    [
        ("/api/v1/sources/file", "register_workspace_csv_source", None),
        ("/api/v1/sources/file/receive", "receive_workspace_file_source", None),
        ("/api/v1/sources/file/backfill", "backfill_workspace_file_history", None),
        ("/api/v1/sources/opcua/browse", "browse_local_opcua", None),
        ("/api/v1/sources/opcua", "register_local_opcua", None),
        ("/api/v1/sources/opcua/diagnose", "diagnose_local_opcua", None),
        ("/api/v1/sources/lifecycle", "change_web_source_control", "lifecycle"),
        ("/api/v1/sources/collection", "change_web_source_control", "collection"),
    ],
)
def test_allowlisted_web_route_dispatches_to_exact_existing_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    handler: str,
    kind: str | None,
) -> None:
    calls: list[tuple[object, ...]] = []

    def record(*args: object) -> dict[str, object]:
        calls.append(args)
        return {"accepted": True}

    monkeypatch.setattr(actions, handler, record)
    payload: dict[str, object] = {"source_id": "pump"}
    assert route in actions.WEB_SOURCE_ACTION_ROUTES
    assert actions.execute_web_source_action(tmp_path, route, payload) == {"accepted": True}
    expected = (tmp_path, payload) if kind is None else (tmp_path, kind, payload)
    assert calls == [expected]


@pytest.mark.parametrize(
    "route",
    [
        "/api/v1/sources/file/other",
        "/api/v1/sources/collection/",
        "/api/v1/review/approve",
        "/api/v1/sources/collection?target=run",
        "../sources/file",
        "",
    ],
)
def test_unknown_web_action_is_rejected_before_any_write(tmp_path: Path, route: str) -> None:
    with pytest.raises(ValueError, match="unknown Web source action"):
        actions.execute_web_source_action(tmp_path, route, {})
