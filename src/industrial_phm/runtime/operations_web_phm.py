"""PHM monitoring read routes for the supervised Web (ADR-0025).

These routes read the PHM store directly instead of composing the full Operations snapshot, so
polling the anomaly screen stays cheap. Responses never contain filesystem paths.
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
from industrial_phm.application.history_window import project_history_window
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import PhmExplanationStore
from industrial_phm.application.phm_range import range_analysis
from industrial_phm.application.phm_read import (
    PhmReadError,
    project_phm_bindings,
    project_phm_monitor,
    project_phm_result,
    project_phm_series,
    project_phm_trace,
    project_snapshot_preview,
)
from industrial_phm.application.phm_signal_comparison import (
    feature_comparison,
    stream_amplitude_unit,
    with_units,
)
from industrial_phm.application.phm_window_read import project_monitor_window, project_phm_window
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.history.ducklake import DuckLakeAssetHistoryConfig
from industrial_phm.models.package import StepKind
from industrial_phm.runtime.operations_web_phm_models import project_phm_models
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

PHM_READ_ROUTES = frozenset(
    {
        "/api/v1/phm/bindings",
        "/api/v1/phm/models",
        "/api/v1/phm/range",
        "/api/v1/phm/comparison",
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
            # Poll only PHM measurements/model progress. Human review is an opt-in
            # workflow with separate read routes, not a 3-second monitoring dependency.
            return HTTPStatus.OK, project_phm_monitor(
                store, workspace.models_path, snapshots, windows=windows
            )
        if path == "/api/v1/phm/bindings":
            return HTTPStatus.OK, project_phm_bindings(
                store, workspace.models_path, snapshots, windows=windows
            )
        if path == "/api/v1/phm/models":
            return HTTPStatus.OK, project_phm_models(workspace, _required_id(params, "asset_id"))
        binding_id = _required_id(params, "binding_id")
        if path in {"/api/v1/phm/comparison", "/api/v1/phm/explanations"}:
            owner = next((b for b in store.list_bindings() if b.binding_id == binding_id), None)
            amplitude = (
                stream_amplitude_unit(snapshots, owner.source_id, owner.asset_id)
                if owner is not None and owner.step_kind == StepKind.ACQUISITION_SNAPSHOT
                else None
            )
        if path == "/api/v1/phm/comparison":
            position = _int(params, "position", default=None, minimum=1)
            previous_position = (
                _int(params, "compare_position", default=None, minimum=1)
                if "compare_position" in params
                else None
            )
            current = store.get_result(binding_id, position)
            previous = (
                store.get_result(binding_id, previous_position)
                if previous_position is not None
                else None
            )
            if (
                current is None
                or (
                    previous_position is not None
                    and (previous is None or previous_position >= position)
                )
                or current.state.value != "analyzed"
                or (previous is not None and previous.state.value != "analyzed")
            ):
                raise PhmReadError("comparison needs two stored analyzed results in order")
            return HTTPStatus.OK, {
                "schema_version": 1,
                "binding_id": binding_id,
                "position": position,
                "analysis_run_id": current.analysis_run_id,
                "compare_position": previous_position,
                "previous_analysis_run_id": previous.analysis_run_id if previous else None,
                "previous_score": previous.output.get("score") if previous else None,
                "features": with_units(feature_comparison(current, previous), amplitude),
            }
        if path == "/api/v1/phm/trace":
            return HTTPStatus.OK, project_phm_trace(store, binding_id=binding_id)
        if path == "/api/v1/phm/range":
            first = _int(params, "from", default=None, minimum=1)
            last = _int(params, "to", default=None, minimum=1)
            binding = next((b for b in store.list_bindings() if b.binding_id == binding_id), None)
            current, previous = (
                store.get_result(binding_id, last),
                store.get_result(binding_id, first),
            )
            if binding is None:
                raise PhmReadError("unknown binding")
            if first >= last or current is None or previous is None:
                raise PhmReadError("range needs two stored results in order")
            names = [row["feature"] for row in feature_comparison(current, previous)[:8]]
            return HTTPStatus.OK, {
                "schema_version": 1,
                "binding_id": binding_id,
                **range_analysis(store, binding_id, binding.step_kind, first, last, names),
            }
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
                        "decision": None if e.decision is None else e.decision.value,
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
            # Units are added on read, so explanations stored before units existed show them too.
            for record in explanations:
                context = record.get("context")
                comparison = context.get("signal_comparison") if isinstance(context, dict) else None
                if isinstance(comparison, dict) and isinstance(comparison.get("features"), list):
                    comparison["features"] = with_units(comparison["features"], amplitude)
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
            position = _int(params, "position", default=None, minimum=1)
            owner = next((b for b in store.list_bindings() if b.binding_id == binding_id), None)
            if owner is not None and owner.step_kind is StepKind.HISTORY_WINDOW:
                if not workspace.history_catalog_path.is_file():
                    return HTTPStatus.OK, {"available": False, "reason": "no stored history"}
                history = DuckLakeAssetHistory(
                    DuckLakeAssetHistoryConfig(
                        workspace.history_catalog_path, workspace.history_data_path
                    )
                )
                return HTTPStatus.OK, project_history_window(
                    store, history, binding_id=binding_id, position=position
                )
            return HTTPStatus.OK, project_phm_window(
                store,
                SqliteObservationWindowRepository(workspace.window_state_path),
                binding_id=binding_id,
                position=position,
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
