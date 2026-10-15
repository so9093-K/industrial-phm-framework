"""What one asset's stored data supports, decided from the stores themselves.

The Web shows this list where data arrives (the asset overview and the end of the CSV flow), so a
user learns which analyses open right away, which need a model connection, and which this data
cannot support and why, before opening each screen. The decisions use the same facts the
analyses use: stored history, delivered acquisitions, installed packages and their declared
inputs, connected models and their stored results, and whether this Web may ask questions.
Nothing here runs an analysis or a model.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from industrial_phm.application import JsonSourceRepository, OpcUaSourceConfig
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.models.package import ModelTask
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_explore import explore_sources, package_task
from industrial_phm.runtime.operations_web_phm_models import project_phm_models
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

CAPABILITIES_ROUTE = "/api/v1/explore/capabilities"

READY = "ready"
NEEDS_CONNECTION = "needs-connection"
WAITING = "waiting"
UNAVAILABLE = "unavailable"


def handle_capabilities_read(
    workspace: OperationsWorkspace, raw_query: str, *, can_ask: bool
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        values = parse_qs(raw_query, strict_parsing=False).get("asset_id", [])
        if len(values) != 1 or not 0 < len(values[0]) <= 512:
            raise ValueError("one asset_id is required")
        asset_id = values[0]
        return HTTPStatus.OK, project_asset_capabilities(workspace, asset_id, can_ask=can_ask)
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_capabilities_query"}
    except OperationsReadError, PhmAnalysisError, OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "capabilities_store_unavailable"}


def project_asset_capabilities(
    workspace: OperationsWorkspace, asset_id: str, *, can_ask: bool
) -> dict[str, Any]:
    """Each analysis with ready / needs-connection / waiting / unavailable and the reason."""
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    explore = explore_sources(workspace, store, asset_id)
    history, acquisition = explore["history"], explore["acquisition"]
    models = project_phm_models(workspace, asset_id)
    waveform_streams = [s for s in models["streams"] if s["kind"] == "acquisition-snapshot"]
    data = {
        "history": None
        if history is None
        else {
            "channel_count": len(history["channels"]),
            "measurement_count": history["measurement_count"],
            "start_at": history["start_at"],
            "end_at": history["end_at"],
            "origins": _origins(workspace, asset_id),
        },
        "acquisition": None
        if not waveform_streams
        else {
            "analyzed_count": acquisition["count"] if acquisition else 0,
            "first": acquisition["first"] if acquisition else None,
            "last": acquisition["last"] if acquisition else None,
            "recorded_replay": any(s["recorded_replay"] for s in waveform_streams),
            "channels": waveform_streams[0]["channels"],
            "sampling_rate_hz": waveform_streams[0]["sampling_rate_hz"],
        },
        "waiting_sources": sum(s["input_state"] == "waiting-input" for s in models["streams"]),
    }
    signals = _signal_capabilities(data, acquisition)
    anomaly = _model_capability("anomaly", ModelTask.ANOMALY_SCORE, workspace, store, models)
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "data": data,
        "capabilities": [*signals, anomaly, _question_capability(anomaly, can_ask)],
        "meaning": "what-the-stored-data-supports-not-asset-health",
    }


def _origins(workspace: OperationsWorkspace, asset_id: str) -> list[str]:
    if not workspace.source_registry_path.is_file():
        return []
    kinds = {
        "opcua" if isinstance(source.config, OpcUaSourceConfig) else "file"
        for source in JsonSourceRepository(workspace.source_registry_path).list_sources()
        if source.asset_id == asset_id
    }
    return sorted(kinds)


def _item(
    capability: str,
    status: str,
    reason: str,
    view: str | None,
    goal: str | None = None,
    **facts: object,
) -> dict[str, Any]:
    return {
        "id": capability,
        "status": status,
        "reason": reason,
        "target": None if view is None else {"view": view, "goal": goal},
        "facts": facts,
    }


def _signal_capabilities(
    data: dict[str, Any], acquisition: dict[str, Any] | None
) -> list[dict[str, Any]]:
    history = data["history"]
    channels = history["channel_count"] if history else 0
    spans_time = bool(history) and datetime.fromisoformat(
        history["start_at"]
    ) < datetime.fromisoformat(history["end_at"])
    analyzed = acquisition["count"] if acquisition else 0
    features = len(acquisition["features"]) if acquisition else 0
    waveforms = data["acquisition"] is not None or acquisition is not None
    # Without stored measurements every signal analysis has the same missing step.
    if history is None and not waveforms:
        reason = "not-received" if data["waiting_sources"] else "no-data"
        return [
            _item(name, UNAVAILABLE, reason, "connect")
            for name in ("measurements", "period-compare", "relation", "spectrum")
        ]
    # Acquisition features exist only once a connected model has read each waveform.
    unread = waveforms and acquisition is None
    items = []
    if history:
        items.append(_item("measurements", READY, "history", "signals", "trend", channels=channels))
    elif acquisition:
        items.append(_item("measurements", READY, "acquisition", "monitor", count=analyzed))
    else:
        items.append(_item("measurements", NEEDS_CONNECTION, "waveforms-need-model", "anomaly"))

    if spans_time:
        items.append(_item("period-compare", READY, "history", "signals", "compare"))
    elif acquisition and analyzed >= 2:
        items.append(_item("period-compare", READY, "acquisition", "signals", "compare"))
    elif acquisition:
        items.append(_item("period-compare", WAITING, "few-acquisitions", None, count=analyzed))
    elif unread:
        items.append(_item("period-compare", NEEDS_CONNECTION, "waveforms-need-model", "anomaly"))
    else:
        items.append(_item("period-compare", UNAVAILABLE, "single-moment", None))

    if history and channels >= 2:
        items.append(_item("relation", READY, "history", "signals", "relation", channels=channels))
    elif acquisition and features >= 2 and analyzed >= 3:
        items.append(_item("relation", READY, "acquisition", "signals", "relation"))
    elif acquisition:
        items.append(_item("relation", WAITING, "few-acquisitions", None, count=analyzed))
    elif unread:
        items.append(_item("relation", NEEDS_CONNECTION, "waveforms-need-model", "anomaly"))
    else:
        items.append(_item("relation", UNAVAILABLE, "single-signal", None))

    if acquisition:
        items.append(_item("spectrum", READY, "acquisition", "signals", "spectrum"))
    elif unread:
        items.append(_item("spectrum", NEEDS_CONNECTION, "waveforms-need-model", "anomaly"))
    else:
        items.append(_item("spectrum", UNAVAILABLE, "no-waveform", None))
    return items


def _model_capability(
    name: str,
    task: ModelTask,
    workspace: OperationsWorkspace,
    store: SqlitePhmAnalysisStore,
    models: dict[str, Any],
) -> dict[str, Any]:
    bindings = (
        [
            binding
            for binding in store.list_bindings()
            if binding.asset_id == models["asset_id"]
            and package_task(workspace, binding.package_id) == task.value
        ]
        if store.path.exists()
        else []
    )
    if bindings:
        counts = {
            binding.binding_id: store.count_between(binding.binding_id, 0, 2**62).get("analyzed", 0)
            for binding in bindings
        }
        best = max(bindings, key=lambda binding: counts[binding.binding_id])
        analyzed = counts[best.binding_id]
        return _item(
            name,
            READY if analyzed else WAITING,
            "connected" if analyzed else "waiting-results",
            name,
            results=analyzed,
            binding_id=best.binding_id,
            package_id=best.package_id,
            recorded_replay=best.recorded_replay,
        )
    packages = [package for package in models["packages"] if package["task"] == task.value]
    fitting = {
        package["package_id"]
        for package in packages
        for candidate in package["candidates"]
        if candidate["compatible"] and not candidate["connected"]
    }
    if fitting:
        return _item(name, NEEDS_CONNECTION, "compatible-model", name, packages=len(fitting))
    if not packages:
        return _item(name, UNAVAILABLE, "no-model-package", None)
    if not models["streams"]:
        return _item(name, UNAVAILABLE, "no-model-input", None)
    reasons = sorted(
        {
            candidate["reason"]
            for package in packages
            for candidate in package["candidates"]
            if candidate["reason"]
        }
    )
    return _item(name, UNAVAILABLE, "input-mismatch", None, details=reasons[:3])


def _question_capability(anomaly: dict[str, Any], can_ask: bool) -> dict[str, Any]:
    if anomaly["status"] != READY:
        waiting = anomaly["status"] == WAITING
        return _item(
            "ai-question", UNAVAILABLE, "waiting-results" if waiting else "needs-results", None
        )
    if not can_ask:
        return _item("ai-question", UNAVAILABLE, "read-only", "anomaly")
    return _item("ai-question", READY, "model-results", "anomaly", "ask")
