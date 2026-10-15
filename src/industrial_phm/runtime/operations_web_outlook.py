"""Read-only condition outlook of one stored signal: degradation, remaining margin, evidence.

The same series the forecast reads (1,000 buckets of one signal identity, or analyzed
acquisition features on the acquisition axis) is measured against its own early baseline and
forecast towards the management level and end condition the user sets. Nothing is stored.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from industrial_phm.application.condition_outlook import degradation, linear_reach
from industrial_phm.application.forecast import (
    DEFAULT_CHANGEPOINT_PRIOR_SCALE,
    DEFAULT_CHANGEPOINT_RANGE,
    HISTORY_PER_HORIZON,
    MIN_POINTS,
    ForecastUnavailable,
    limit_reach,
)
from industrial_phm.application.outlook_text import outlook_facts, outlook_sentences
from industrial_phm.application.phm_analysis import (
    PhmAnalysisError,
    SqlitePhmAnalysisStore,
    StepState,
)
from industrial_phm.models.package import ModelTask
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_explore import package_task
from industrial_phm.runtime.operations_web_forecast import (
    _ORIGIN,
    acquisition_points,
    history_points,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

OUTLOOK_ROUTE = "/api/v1/outlook"
# A forecast that follows trend changes readily, for comparison with the chosen settings.
RESPONSIVE_PRIOR = 0.3
RECENT_SHARE = 0.3
_TIME_STEPS = 400
RECENT_RESULTS = 10


def handle_outlook_read(
    workspace: OperationsWorkspace, raw_query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        query = parse_qs(raw_query, strict_parsing=False)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError("repeated query parameter")
        params = {name: values[0] for name, values in query.items()}
        return HTTPStatus.OK, condition_outlook(workspace, **outlook_arguments(params))
    except ForecastUnavailable as error:
        return HTTPStatus.UNPROCESSABLE_ENTITY, {
            "error": "outlook_unavailable",
            "reason": error.reason,
        }
    except LookupError:
        return HTTPStatus.NOT_FOUND, {"error": "nothing_to_outlook"}
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_outlook_query"}
    except OperationsReadError, PhmAnalysisError, OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "outlook_store_unavailable"}


def outlook_arguments(params: dict[str, str]) -> dict[str, Any]:
    """The outlook a query names, checked against the same ranges as the forecast."""
    asset_id = params.get("asset_id", "")
    if not 0 < len(asset_id) <= 512:
        raise ValueError("asset_id is required")
    kind = params.get("kind", "")
    if kind not in {"history", "acquisition"} or not 0 < len(params.get("series", "")) <= 512:
        raise ValueError("kind and series are required")
    direction = params.get("direction", "upper")
    if direction not in {"upper", "lower"}:
        raise ValueError("invalid direction")
    limits = {
        name: _finite(params[key])
        for name, key in (("management", "management_limit"), ("end", "end_limit"))
        if params.get(key)
    }
    prior = _finite(params.get("changepoint_prior_scale", str(DEFAULT_CHANGEPOINT_PRIOR_SCALE)))
    change_range = _finite(params.get("changepoint_range", str(DEFAULT_CHANGEPOINT_RANGE)))
    training = int(params["training_points"]) if params.get("training_points") else None
    assumed = (
        _finite(params["assumed_period_seconds"]) if params.get("assumed_period_seconds") else None
    )
    seasonality = params.get("seasonality", "auto")
    if (
        not 0.001 <= prior <= 0.5
        or not 0.5 <= change_range <= 0.95
        or (training is not None and not 20 <= training <= 1000)
        or (assumed is not None and (kind != "acquisition" or not 1 <= assumed <= 86400))
        or seasonality not in {"auto", "off"}
    ):
        raise ValueError("forecast setting out of range")
    return {
        "asset_id": asset_id,
        "kind": kind,
        "series": params["series"],
        "limits": limits,
        "upper": direction == "upper",
        "changepoint_prior_scale": prior,
        "changepoint_range": change_range,
        "training_points": training,
        "seasonal": seasonality != "off",
        "assumed_period_seconds": assumed,
    }


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("value must be finite")
    return value


def condition_outlook(
    workspace: OperationsWorkspace,
    asset_id: str,
    *,
    kind: str,
    series: str,
    limits: dict[str, float],
    upper: bool = True,
    changepoint_prior_scale: float = DEFAULT_CHANGEPOINT_PRIOR_SCALE,
    changepoint_range: float = DEFAULT_CHANGEPOINT_RANGE,
    training_points: int | None = None,
    seasonal: bool = True,
    assumed_period_seconds: float | None = None,
) -> dict[str, Any]:
    """Degradation indicator, remaining margin under four readings, and the evidence used."""
    if kind == "history":
        times, values, meta = history_points(workspace, asset_id, series)
    else:
        times, values, meta = acquisition_points(
            workspace,
            asset_id,
            series,
            assumed_period_seconds=assumed_period_seconds,
            count_mode=True,
        )
        seasonal = False
    pairs = [(t, v) for t, v in zip(times, values, strict=True) if math.isfinite(v)]
    if len(pairs) < MIN_POINTS:
        raise ForecastUnavailable("few-points")
    times, values = [t for t, _ in pairs], [v for _, v in pairs]
    acquisitions = kind == "acquisition"
    period = meta.get("period_seconds") or 1.0
    span = (times[-1] - times[0]).total_seconds()
    if acquisitions:
        axis = [1 + (t - _ORIGIN).total_seconds() / period for t in times]
        labels: list[Any] = [round(x) for x in axis]
        rate_unit = "acquisition"
    else:
        rate_unit = "day" if span >= 3 * 86_400 else "hour"
        scale = 86_400 if rate_unit == "day" else 3_600
        axis = [(t - times[0]).total_seconds() / scale for t in times]
        labels = [t.astimezone(UTC).isoformat() for t in times]
    indicator = degradation(axis, values)
    for window in ("baseline", "recent"):
        part = indicator[window]
        part["from"], part["to"] = labels[part["first_index"]], labels[part["last_index"]]
    departure = indicator["departure"]
    if departure is not None:
        since = departure["since_index"]
        departure["since"] = None if since is None else labels[since]

    used = len(values) if training_points is None else min(training_points, len(values))
    train_span = (times[-1] - times[len(values) - used]).total_seconds()
    search_seconds = train_span / HISTORY_PER_HORIZON
    steps = _TIME_STEPS
    if acquisitions:
        steps = max(1, min(2000, math.floor(search_seconds / period)))
        search_seconds = steps * period
    if search_seconds <= 0:
        raise ForecastUnavailable("short-history")

    scenarios = []
    if limits:
        readings = [("current", changepoint_prior_scale, training_points)]
        recent = max(MIN_POINTS, round(len(values) * RECENT_SHARE))
        if recent < used:
            readings.append(("recent", changepoint_prior_scale, recent))
        responsive = (
            RESPONSIVE_PRIOR
            if changepoint_prior_scale < RESPONSIVE_PRIOR
            else DEFAULT_CHANGEPOINT_PRIOR_SCALE
        )
        readings.append(("responsive", responsive, training_points))
        for name, prior, training in readings:
            result = limit_reach(
                times,
                values,
                limits,
                upper=upper,
                search_seconds=search_seconds,
                steps=steps,
                seasonal=seasonal,
                changepoint_prior_scale=prior,
                changepoint_range=changepoint_range,
                training_points=training,
            )
            scenarios.append(
                {
                    "id": name,
                    "changepoint_prior_scale": prior,
                    "training_points": result["points"],
                    **result,
                }
            )
        seconds = [(t - times[0]).total_seconds() for t in times]
        scenarios.append(
            {
                "id": "linear",
                **linear_reach(seconds, values, limits, upper=upper, search_seconds=search_seconds),
            }
        )
        for scenario in scenarios:
            for reached in scenario["limits"].values():
                for key in ("expected", "earliest", "latest"):
                    if reached[key] is not None and acquisitions:
                        # The first whole acquisition at or after the reaching point.
                        reached[key] = math.ceil(reached[key] / period - 1e-6)

    anomaly = anomaly_evidence(
        workspace,
        asset_id,
        source_id=meta["source_id"],
        measurement_point_id=meta.get("measurement_point_id"),
        kind=kind,
        feature=series,
    )
    # The AI briefing must be tied to the exact observations and anomaly evidence
    # that produced this outlook, not merely the same selected form fields.
    revision = hashlib.sha256(
        json.dumps(
            {
                "measurements": [(t.isoformat(), v) for t, v in zip(times, values, strict=True)],
                "source_id": meta["source_id"],
                "measurement_point_id": meta.get("measurement_point_id"),
                "anomaly": anomaly,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    body = {
        "data_version": revision,
        "schema_version": 1,
        "asset_id": asset_id,
        "kind": kind,
        "series": series,
        "axis": "acquisition" if acquisitions else "time",
        **meta,
        "record": {"first": labels[0], "last": labels[-1], "points": len(values)},
        "rate_unit": rate_unit,
        "degradation": indicator,
        "conditions": {
            "direction": "upper" if upper else "lower",
            "management": limits.get("management"),
            "end": limits.get("end"),
        },
        "settings": {
            "changepoint_prior_scale": changepoint_prior_scale,
            "changepoint_range": changepoint_range,
            "training_points": training_points,
            "seasonality": "auto" if seasonal else "off",
        },
        "search": {
            "seconds": search_seconds,
            "acquisitions": steps if acquisitions else None,
            "until": round(axis[-1]) + steps
            if acquisitions
            else (times[-1] + timedelta(seconds=search_seconds)).astimezone(UTC).isoformat(),
        },
        "offset_unit": "acquisition" if acquisitions else "second",
        "scenarios": scenarios,
        "anomaly_model": anomaly,
        "meaning": "remaining-margin-to-user-conditions-not-a-diagnosis",
    }
    # The screen's sentences and the facts an AI briefing may use, worded once.
    body["sentences"] = outlook_sentences(body)
    body["facts"] = outlook_facts(body)
    return body


def anomaly_evidence(
    workspace: OperationsWorkspace,
    asset_id: str,
    *,
    source_id: str,
    measurement_point_id: str | None,
    kind: str,
    feature: str,
) -> dict[str, Any] | None:
    """Only connect analysis evidence from the selected signal's source and input axis."""
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    if not store.path.exists():
        return None
    bindings = [
        binding
        for binding in store.list_bindings()
        if binding.asset_id == asset_id
        and binding.source_id == source_id
        and (measurement_point_id is None or binding.measurement_point_id == measurement_point_id)
        and binding.step_kind.value
        == ("acquisition-snapshot" if kind == "acquisition" else "observation-window")
        and package_task(workspace, binding.package_id) == ModelTask.ANOMALY_SCORE.value
        and (
            kind != "acquisition"
            or _package_uses_feature(workspace, binding.package_id, feature)
        )
    ]
    if not bindings:
        return None
    counts = {
        binding.binding_id: store.count_between(binding.binding_id, 0, 2**62).get("analyzed", 0)
        for binding in bindings
    }
    best = max(bindings, key=lambda binding: counts[binding.binding_id])
    latest = store.latest_result(best.binding_id, state=StepState.ANALYZED)
    intervals = store.list_intervals(best.binding_id)
    exceeding_count, first_exceeding = store.analyzed_threshold_exceedance(best.binding_id)
    recent = store.recent_analyzed(best.binding_id, limit=RECENT_RESULTS)

    def at(value: datetime | None) -> str | None:
        return None if value is None else value.astimezone(UTC).isoformat()

    output = dict(latest.output) if latest is not None else {}
    return {
        "binding_id": best.binding_id,
        "package_id": best.package_id,
        "step_kind": best.step_kind,
        "results": counts[best.binding_id],
        "read": counts[best.binding_id],
        "exceeding": exceeding_count,
        "first_exceeding": None
        if first_exceeding is None
        else {
            "position": first_exceeding.position,
            "at": at(first_exceeding.event_start),
        },
        "recent": {
            "results": len(recent),
            "exceeding": sum(r.output.get("exceeds_threshold") is True for r in recent),
        },
        "latest": None
        if latest is None
        else {
            "position": latest.position,
            "at": at(latest.event_start),
            "score": output.get("score"),
            "threshold": output.get("threshold"),
            "exceeds": output.get("exceeds_threshold"),
        },
        "intervals": [
            {
                "start_position": interval.start_position,
                "end_position": interval.end_position,
                "start_at": at(interval.start_event_at),
                "steps": interval.step_count,
                "peak_score": interval.peak_score,
                "open": interval.open,
            }
            for interval in intervals[-5:]
        ],
        "interval_count": len(intervals),
    }


def _package_uses_feature(
    workspace: OperationsWorkspace, package_id: str, feature: str
) -> bool:
    """Only show model scores tied to the selected feature in the declared package input."""
    try:
        manifest = json.loads((workspace.models_path / package_id / "package.json").read_text())
        names = manifest["input"]["feature_names"]
    except (OSError, ValueError, TypeError, KeyError):
        return False
    return isinstance(names, list) and feature in names
