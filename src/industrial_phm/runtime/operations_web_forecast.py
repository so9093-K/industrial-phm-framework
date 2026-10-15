"""Read-only forecast routes: which series an asset can forecast, and one forecast.

Stored history is read as at most 1,000 time buckets of one signal identity (source, point and
meaning are never mixed); vibration acquisitions use their analyzed features on the
acquisition interval. Nothing is stored: a forecast is computed when asked.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.forecast import (
    HORIZONS,
    ForecastUnavailable,
    forecast_values,
    horizon_reasons,
)
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.application.phm_signal_comparison import feature_label
from industrial_phm.application.signal_exploration import (
    acquisition_binding,
    interpretation_unit,
    strongest_identity,
)
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_explore import _history, explore_sources
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

FORECAST_ROUTES = frozenset({"/api/v1/forecast/options", "/api/v1/forecast"})
_BUCKETS = 1000
# Acquisitions are placed on a time axis by their recorded interval; the origin is arbitrary
# and only positions are reported back.
_ORIGIN = datetime(2000, 1, 1, tzinfo=UTC)


def handle_forecast_read(
    workspace: OperationsWorkspace, path: str, raw_query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        query = parse_qs(raw_query, strict_parsing=False)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError("repeated query parameter")
        params = {name: values[0] for name, values in query.items()}
        asset_id = params.get("asset_id", "")
        if not 0 < len(asset_id) <= 512:
            raise ValueError("asset_id is required")
        if path == "/api/v1/forecast/options":
            return HTTPStatus.OK, forecast_options(workspace, asset_id)
        horizon = params.get("horizon", "")
        if horizon not in {*HORIZONS, "count"}:
            raise ValueError("unknown horizon")
        kind = params.get("kind", "")
        if horizon == "count" and kind != "acquisition":
            raise ValueError("acquisition count forecast requires acquisition data")
        count = int(params["horizon_count"]) if horizon == "count" else None
        if count is not None and not 1 <= count <= 2000:
            raise ValueError("horizon_count must be 1..2000")
        assumed_period = (
            float(params["assumed_period_seconds"])
            if params.get("assumed_period_seconds")
            else None
        )
        if assumed_period is not None and (
            kind != "acquisition"
            or not math.isfinite(assumed_period)
            or not 1 <= assumed_period <= 86400
        ):
            raise ValueError("invalid assumed_period_seconds")
        prior_scale = float(params.get("changepoint_prior_scale", "0.05"))
        change_range = float(params.get("changepoint_range", "0.9"))
        training_points = int(params["training_points"]) if params.get("training_points") else None
        seasonality = params.get("seasonality", "auto")
        backtest = params.get("backtest", "one")
        if backtest not in {"one", "multi"}:
            raise ValueError("invalid backtest")
        if seasonality not in {"auto", "off"}:
            raise ValueError("invalid seasonality")
        if not math.isfinite(prior_scale) or not 0.001 <= prior_scale <= 0.5:
            raise ValueError("invalid changepoint_prior_scale")
        if not math.isfinite(change_range) or not 0.5 <= change_range <= 0.95:
            raise ValueError("invalid changepoint_range")
        if training_points is not None and not 20 <= training_points <= 1000:
            raise ValueError("invalid training_points")
        threshold = float(params["threshold"]) if params.get("threshold") else None
        if threshold is not None and not math.isfinite(threshold):
            raise ValueError("threshold must be finite")
        return HTTPStatus.OK, forecast_series(
            workspace,
            asset_id,
            kind=kind,
            series=params.get("series", ""),
            horizon=horizon,
            threshold=threshold,
            changepoint_prior_scale=prior_scale,
            changepoint_range=change_range,
            training_points=training_points,
            seasonality=seasonality,
            horizon_count=count,
            assumed_period_seconds=assumed_period,
            rolling_backtests=backtest == "multi",
        )
    except ForecastUnavailable as error:
        return HTTPStatus.UNPROCESSABLE_ENTITY, {
            "error": "forecast_unavailable",
            "reason": error.reason,
        }
    except LookupError:
        return HTTPStatus.NOT_FOUND, {"error": "nothing_to_forecast"}
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_forecast_query"}
    except OperationsReadError, PhmAnalysisError, OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "forecast_store_unavailable"}


def _period(workspace: OperationsWorkspace, asset_id: str, source_id: str) -> float | None:
    for stream in SqliteAcquisitionSnapshotRepository(
        workspace.acquisition_snapshot_path
    ).list_streams():
        if stream.asset_id == asset_id and stream.source_id == source_id:
            return stream.acquisition_period_seconds
    return None


def forecast_options(workspace: OperationsWorkspace, asset_id: str) -> dict[str, Any]:
    """The series each kind of stored data offers, and which horizons its length supports."""
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    sources = explore_sources(workspace, store, asset_id)
    history = sources["history"]
    acquisition = sources["acquisition"]
    body: dict[str, Any] = {"schema_version": 1, "asset_id": asset_id}
    if history is not None:
        span = (
            datetime.fromisoformat(history["end_at"]) - datetime.fromisoformat(history["start_at"])
        ).total_seconds()
        body["history"] = {
            "series": [{"key": channel, "label": channel} for channel in history["channels"]],
            "start_at": history["start_at"],
            "end_at": history["end_at"],
            "horizons": horizon_reasons(span, history["measurement_count"]),
        }
    else:
        body["history"] = None
    period = (
        _period(workspace, asset_id, acquisition["source_id"]) if acquisition is not None else None
    )
    if acquisition is not None:
        span = (acquisition["last"] - acquisition["first"]) * (period or 1)
        body["acquisition"] = {
            "series": acquisition["features"],
            "first": acquisition["first"],
            "last": acquisition["last"],
            "count": acquisition["count"],
            "period_seconds": period,
            "horizons": (
                horizon_reasons(span, acquisition["count"])
                if period
                else {key: "unknown-interval" for key in HORIZONS}
            ),
            "count_forecast": acquisition["count"] >= 20,
        }
    else:
        body["acquisition"] = None
    return body


def forecast_series(
    workspace: OperationsWorkspace,
    asset_id: str,
    *,
    kind: str,
    series: str,
    horizon: str,
    threshold: float | None,
    changepoint_prior_scale: float = 0.05,
    changepoint_range: float = 0.9,
    training_points: int | None = None,
    seasonality: str = "auto",
    horizon_count: int | None = None,
    assumed_period_seconds: float | None = None,
    rolling_backtests: bool = False,
) -> dict[str, Any]:
    """One series continued ``horizon`` ahead, with its interval and a check on the past."""
    if not series:
        raise ValueError("series is required")
    if kind == "history":
        if horizon == "count" or assumed_period_seconds is not None:
            raise ValueError("count mode only applies to acquisitions")
        times, values, meta = _history_points(workspace, asset_id, series)
        seasonal = seasonality != "off"
    elif kind == "acquisition":
        times, values, meta = _acquisition_points(
            workspace,
            asset_id,
            series,
            assumed_period_seconds=assumed_period_seconds,
            count_mode=horizon == "count",
        )
        seasonal = False
    else:
        raise ValueError("unknown forecast kind")
    period = meta.get("period_seconds")
    seconds = (
        round(horizon_count * period)
        if horizon == "count" and period is not None and horizon_count is not None
        else HORIZONS.get(horizon)
    )
    if seconds is None or seconds <= 0:
        raise ValueError("invalid prediction horizon")
    result = forecast_values(
        times,
        values,
        seconds,
        seasonal=seasonal,
        threshold=threshold,
        changepoint_prior_scale=changepoint_prior_scale,
        changepoint_range=changepoint_range,
        training_points=training_points,
        rolling_backtests=rolling_backtests,
    )
    if kind == "acquisition":
        # Report the acquisition axis back: an acquisition's position, not an invented clock.
        period = meta["period_seconds"]

        def position(iso: str) -> float:
            return float(1 + (datetime.fromisoformat(iso) - _ORIGIN).total_seconds() / period)

        result["history"] = [[position(t), v] for t, v in result["history"]]
        result["fitted"] = [[position(t), v] for t, v in result["fitted"]]
        result["forecast"] = [[position(t), *rest] for t, *rest in result["forecast"]]
        if result["threshold"]:
            for key in ("expected_at", "earliest_at"):
                if result["threshold"].get(key):
                    result["threshold"][key] = position(result["threshold"][key])
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "kind": kind,
        "series": series,
        "horizon": horizon,
        "horizon_count": horizon_count,
        "forecast_seconds": seconds,
        "axis": "acquisition" if kind == "acquisition" else "time",
        **meta,
        **result,
        "meaning": "stored-flow-continued-not-failure-time-or-remaining-life",
    }


def _history_points(
    workspace: OperationsWorkspace, asset_id: str, channel: str
) -> tuple[list[datetime], list[float], dict[str, Any]]:
    reader = _history(workspace)
    if reader is None:
        raise LookupError("no stored measurement history")
    summary = next((a for a in reader.list_history_assets() if a.asset_id == asset_id), None)
    if summary is None:
        raise LookupError("no stored measurement history")
    aggregation = reader.query_measurement_aggregation(
        asset_id,
        channel_id=channel,
        start_at=summary.start_at,
        end_at=summary.end_at + timedelta(seconds=1),
        bucket_count=_BUCKETS,
    )
    key, buckets = strongest_identity(aggregation.buckets)
    points = sorted(
        (b.first_event_at + (b.last_event_at - b.first_event_at) / 2, float(b.mean))
        for b in buckets
        if b.mean is not None
    )
    return (
        [t for t, _ in points],
        [v for _, v in points],
        {
            "label": channel,
            "unit": interpretation_unit(key[2]),
            "source_id": key[0],
            "measurement_point_id": key[1],
            "raw_count": sum(b.usable_count for b in buckets),
            "bucket_seconds": aggregation.bucket_seconds,
            "other_identities": len(
                {
                    (b.source_id, b.measurement_point_id, b.interpretation_json)
                    for b in aggregation.buckets
                }
            )
            - 1,
        },
    )


def _acquisition_points(
    workspace: OperationsWorkspace,
    asset_id: str,
    feature: str,
    *,
    assumed_period_seconds: float | None = None,
    count_mode: bool = False,
) -> tuple[list[datetime], list[float], dict[str, Any]]:
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = acquisition_binding(store, asset_id) if store.path.exists() else None
    if binding is None:
        raise LookupError("no analyzed acquisitions")
    recorded_period = _period(workspace, asset_id, binding.source_id)
    if not recorded_period and not count_mode and assumed_period_seconds is None:
        raise ForecastUnavailable("unknown-interval")
    # In count mode an ordinal always has a well-defined next step, even without a clock.
    period = assumed_period_seconds or recorded_period or 1.0
    results, total = store.analyzed_between(binding.binding_id, 0, 2**62, max_points=_BUCKETS)
    points = [
        (r.position, float(value))
        for r in results
        if isinstance(value := (r.features or {}).get(feature), (int, float))
        and math.isfinite(float(value))
    ]
    if not points:
        raise LookupError("no stored values for this feature")
    return (
        [_ORIGIN + timedelta(seconds=(position - 1) * period) for position, _ in points],
        [value for _, value in points],
        {
            "label": feature_label(feature),
            "unit": None,
            "source_id": binding.source_id,
            "measurement_point_id": None,
            "raw_count": total,
            "period_seconds": period,
            "recorded_period_seconds": recorded_period,
            "assumed_period_seconds": assumed_period_seconds,
            "time_basis": (
                "assumed"
                if assumed_period_seconds is not None
                else "recorded"
                if recorded_period is not None
                else "ordinal"
            ),
        },
    )
