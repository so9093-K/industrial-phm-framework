"""PHM monitoring read routes for the supervised Web (ADR-0025).

These routes read the PHM store directly instead of composing the full Operations snapshot, so
polling the anomaly/RUL screens stays cheap. Responses never contain filesystem paths.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from urllib.parse import parse_qs

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
)
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import (
    PhmReadError,
    project_phm_bindings,
    project_phm_series,
    project_snapshot_preview,
)
from industrial_phm.application.phm_window_read import project_phm_window
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

PHM_READ_ROUTES = frozenset(
    {"/api/v1/phm/bindings", "/api/v1/phm/series", "/api/v1/phm/snapshot", "/api/v1/phm/window"}
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
        if path == "/api/v1/phm/bindings":
            return HTTPStatus.OK, project_phm_bindings(
                store, workspace.models_path, snapshots, windows=windows
            )
        binding_id = _required_id(params, "binding_id")
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
