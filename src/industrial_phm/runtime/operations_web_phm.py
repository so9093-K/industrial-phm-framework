"""PHM monitoring read routes for the supervised Web (ADR-0025).

These routes read the PHM store directly instead of composing the full Operations snapshot, so
polling the anomaly/RUL screens stays cheap. Responses never contain filesystem paths.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from urllib.parse import parse_qs

from industrial_phm.application import JsonFindingReviewRepository, JsonOperationalFindingRepository
from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
)
from industrial_phm.application.maintenance_review import finding_review_status
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import PhmExplanationStore
from industrial_phm.application.phm_read import (
    PhmReadError,
    project_phm_bindings,
    project_phm_monitor,
    project_phm_result,
    project_phm_series,
    project_phm_trace,
    project_snapshot_preview,
)
from industrial_phm.application.phm_window_read import project_monitor_window, project_phm_window
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

PHM_READ_ROUTES = frozenset(
    {
        "/api/v1/phm/bindings",
        "/api/v1/phm/monitor",
        "/api/v1/phm/result",
        "/api/v1/phm/trace",
        "/api/v1/phm/window-input",
        "/api/v1/phm/series",
        "/api/v1/phm/snapshot",
        "/api/v1/phm/window",
        "/api/v1/phm/explanations",
        "/api/v1/phm/review",
    }
)
_MAX_ID_LENGTH = 512


def handle_phm_read(
    workspace: OperationsWorkspace, path: str, query: str
) -> tuple[HTTPStatus, dict[str, object]]:
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    try:
        params = _params(query)
        if path == "/api/v1/phm/monitor":
            overview = project_phm_monitor(store, workspace.models_path, snapshots, windows=windows)
            try:
                findings = [
                    item
                    for item in JsonOperationalFindingRepository(
                        workspace.finding_state_path
                    ).list_findings()
                    if item.finding_semantics_id == "phm-human-review-request-v1"
                ]
                events = JsonFindingReviewRepository(
                    workspace.maintenance_review_state_path
                ).list_events()
                statuses = {
                    item.finding_id: finding_review_status(events, item.finding_id).value
                    for item in findings
                }
                overview["reviews"] = {
                    state: sum(value == state for value in statuses.values())
                    for state in ("open", "acknowledged", "closed")
                }
                for item in overview["items"]:
                    latest = item["latest_analyzed"]
                    item["latest_review_status"] = (
                        statuses.get("finding-phm-" + latest["analysis_run_id"]) if latest else None
                    )
                overview["review_read_error"] = False
            except ValueError, OSError:
                overview["reviews"] = None
                overview["review_read_error"] = True
            return HTTPStatus.OK, overview
        if path == "/api/v1/phm/bindings":
            return HTTPStatus.OK, project_phm_bindings(
                store, workspace.models_path, snapshots, windows=windows
            )
        binding_id = _required_id(params, "binding_id")
        if path == "/api/v1/phm/trace":
            return HTTPStatus.OK, project_phm_trace(store, binding_id=binding_id)
        if path == "/api/v1/phm/window-input":
            return HTTPStatus.OK, project_monitor_window(
                store,
                windows,
                binding_id=binding_id,
                position=_int(params, "position", default=None, minimum=1),
            )
        if path == "/api/v1/phm/result":
            return HTTPStatus.OK, project_phm_result(
                store,
                binding_id=binding_id,
                position=_int(params, "position", default=None, minimum=1),
            )
        if path == "/api/v1/phm/review":
            result = store.get_result(binding_id, _int(params, "position", default=None, minimum=1))
            if result is None:
                raise PhmReadError("step unavailable")
            identifier = "finding-phm-" + result.analysis_run_id
            finding = next(
                (
                    f
                    for f in JsonOperationalFindingRepository(
                        workspace.finding_state_path
                    ).list_findings()
                    if f.finding_id == identifier
                ),
                None,
            )
            reviews = JsonFindingReviewRepository(workspace.maintenance_review_state_path)
            return HTTPStatus.OK, {
                "finding_id": identifier if finding else None,
                "status": reviews.status_for(identifier).value if finding else None,
                "events": [
                    {
                        "action": e.action.value,
                        "note": e.note,
                        "recorded_at": e.recorded_at.isoformat(),
                    }
                    for e in reviews.list_events()
                    if e.finding_id == identifier
                ][-20:],
            }
        if path == "/api/v1/phm/explanations":
            explanations = PhmExplanationStore(workspace.phm_explanation_path).list_for(
                binding_id, _int(params, "position", default=None, minimum=1)
            )
            return HTTPStatus.OK, {"schema_version": 1, "explanations": explanations}
        if path == "/api/v1/phm/series":
            return HTTPStatus.OK, project_phm_series(
                store,
                workspace.models_path,
                snapshots,
                binding_id=binding_id,
                since_change_seq=_int(params, "since", default=0, minimum=0),
                windows=windows,
            )
        if path == "/api/v1/phm/window":
            return HTTPStatus.OK, project_phm_window(
                store,
                SqliteObservationWindowRepository(workspace.window_state_path),
                binding_id=binding_id,
                position=_int(params, "position", default=None, minimum=1),
            )
        return HTTPStatus.OK, project_snapshot_preview(
            store,
            snapshots,
            binding_id=binding_id,
            position=_int(params, "position", default=None, minimum=1),
            bins=_int(params, "bins", default=400, minimum=1),
        )
    except PhmReadError as error:
        code = "unknown_binding" if "unknown binding" in str(error) else "invalid_phm_query"
        status = HTTPStatus.NOT_FOUND if code == "unknown_binding" else HTTPStatus.BAD_REQUEST
        return status, {"error": code}
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_phm_query"}
    except PhmAnalysisError, AcquisitionSnapshotError, OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "phm_store_unavailable"}


def _params(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True, strict_parsing=False)
    if any(len(values) != 1 for values in parsed.values()):
        raise ValueError("repeated query parameter")
    return {key: values[0] for key, values in parsed.items()}


def _required_id(params: dict[str, str], name: str) -> str:
    value = params.get(name, "")
    if not value or len(value) > _MAX_ID_LENGTH or any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {name}")
    return value


def _int(params: dict[str, str], name: str, *, default: int | None, minimum: int) -> int:
    raw = params.get(name)
    if raw is None:
        if default is None:
            raise ValueError(f"{name} is required")
        return default
    if not raw.isdigit():
        raise ValueError(f"invalid {name}")
    value = int(raw)
    if value < minimum:
        raise ValueError(f"{name} below minimum")
    return value
