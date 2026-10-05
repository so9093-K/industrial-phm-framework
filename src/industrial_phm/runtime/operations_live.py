"""Bounded concrete reads for Operations history and live-signal surfaces."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from industrial_phm.application import (
    AcquisitionTelemetrySurface,
    AssetWorkspaceSource,
    LiveObservationView,
    RegisteredSource,
    SourceType,
    build_live_observation_view,
)
from industrial_phm.application.measurement_history import (
    HistoryAssetSummary,
    MeasurementHistoryAggregation,
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
)
from industrial_phm.history import (
    DuckLakeAssetHistory,
    DuckLakeAssetHistoryConfig,
    DuckLakeRuntimeUnavailableError,
)
from industrial_phm.runtime.acquisition_spool import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
)
from industrial_phm.runtime.acquisition_telemetry import SqliteAcquisitionTelemetryRepository
from industrial_phm.runtime.operations_app_wiring import OperationsAppPaths

DEFAULT_LIVE_LOOKBACK_SECONDS = 60.0
DEFAULT_LIVE_POINT_BUDGET = 600


class OperationsReadError(RuntimeError):
    """Expected operator-facing failure while reading local Operations evidence."""


def _history_read[T](factory: Callable[[], T]) -> T:
    try:
        return factory()
    except (DuckLakeRuntimeUnavailableError, OSError, TimeoutError, ValueError) as error:
        detail = str(error).strip() or type(error).__name__
        raise OperationsReadError(detail) from error


def list_operations_history_assets(
    history: DuckLakeAssetHistory,
) -> tuple[HistoryAssetSummary, ...]:
    return _history_read(history.list_history_assets)


def list_operations_history_channels(
    history: DuckLakeAssetHistory,
    asset_id: str,
) -> tuple[str, ...]:
    return _history_read(lambda: history.list_history_channels(asset_id))


def query_operations_latest_measurements(
    history: DuckLakeAssetHistory,
    asset_id: str,
    *,
    channel_id: str,
) -> tuple[MeasurementHistoryPoint, ...]:
    return _history_read(
        lambda: history.query_latest_measurements(asset_id, channel_id=channel_id)
    )


def query_operations_measurement_page(
    history: DuckLakeAssetHistory,
    asset_id: str,
    *,
    start_at: datetime,
    end_at: datetime,
    channel_id: str,
    point_budget: int,
    latest: bool,
) -> MeasurementHistoryPage:
    return _history_read(
        lambda: history.query_measurement_page(
            asset_id,
            start_at=start_at,
            end_at=end_at,
            channel_id=channel_id,
            point_budget=point_budget,
            latest=latest,
        )
    )


def query_operations_measurement_aggregation(
    history: DuckLakeAssetHistory,
    asset_id: str,
    *,
    channel_id: str,
    start_at: datetime,
    end_at: datetime,
    bucket_count: int,
) -> MeasurementHistoryAggregation:
    return _history_read(
        lambda: history.query_measurement_aggregation(
            asset_id,
            channel_id=channel_id,
            start_at=start_at,
            end_at=end_at,
            bucket_count=bucket_count,
        )
    )


def load_operations_live_observation(
    paths: OperationsAppPaths,
    *,
    asset_id: str,
    channel_id: str,
    registered_sources: Sequence[RegisteredSource],
    asset_sources: Sequence[AssetWorkspaceSource],
    sampled_at: datetime,
    lookback_seconds: float = DEFAULT_LIVE_LOOKBACK_SECONDS,
    point_budget: int = DEFAULT_LIVE_POINT_BUDGET,
) -> LiveObservationView:
    """Read only the selected live signal; do not reload the full Operations snapshot."""

    if not isinstance(paths, OperationsAppPaths):
        raise ValueError("paths must be OperationsAppPaths")
    if sampled_at.utcoffset() is None:
        raise ValueError("sampled_at must be timezone-aware")
    if (
        isinstance(lookback_seconds, bool)
        or not isinstance(lookback_seconds, (int, float))
        or lookback_seconds <= 0
    ):
        raise ValueError("lookback_seconds must be positive")
    if isinstance(point_budget, bool) or not isinstance(point_budget, int) or point_budget < 1:
        raise ValueError("point_budget must be a positive integer")
    if point_budget > 10000:
        raise ValueError("point_budget must not exceed 10000")

    registered = tuple(registered_sources)
    mapped_source_ids = tuple(
        sorted(
            source.source_id
            for source in registered
            if source.asset_id == asset_id
            and source.source_type == SourceType.OPCUA
            and any(identity.channel_id == channel_id for identity in source.channel_identities)
        )
    )
    latest_points: tuple[MeasurementHistoryPoint, ...] = ()
    recent_page = MeasurementHistoryPage((), False, point_budget)

    if paths.history_catalog.is_file():
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(paths.history_catalog, paths.history_data)
        )
        latest_points = query_operations_latest_measurements(
            history,
            asset_id,
            channel_id=channel_id,
        )
        event_times = tuple(
            point.measurement.event_at
            for point in latest_points
            if point.measurement.source_id in mapped_source_ids
            and point.measurement.event_at is not None
        )
        if event_times:
            end_at = max(event_times) + timedelta(microseconds=1)
            recent_page = query_operations_measurement_page(
                history,
                asset_id,
                channel_id=channel_id,
                start_at=end_at - timedelta(seconds=float(lookback_seconds)),
                end_at=end_at,
                point_budget=point_budget,
                latest=True,
            )

    try:
        surfaces = _load_live_acquisition_surfaces(
            paths,
            source_ids=mapped_source_ids,
            sampled_at=sampled_at,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        detail = str(error).strip() or type(error).__name__
        raise OperationsReadError(detail) from error
    return build_live_observation_view(
        asset_id=asset_id,
        channel_id=channel_id,
        registered_sources=registered,
        asset_sources=asset_sources,
        acquisition_surfaces=surfaces,
        latest_points=latest_points,
        recent_page=recent_page,
        sampled_at=sampled_at,
    )


def _load_live_acquisition_surfaces(
    paths: OperationsAppPaths,
    *,
    source_ids: Sequence[str],
    sampled_at: datetime,
) -> tuple[AcquisitionTelemetrySurface, ...]:
    if not source_ids or not paths.acquisition_telemetry.is_file():
        return ()
    if not paths.acquisition_spool.is_file():
        return ()

    telemetry = SqliteAcquisitionTelemetryRepository(paths.acquisition_telemetry)
    spool = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(path=paths.acquisition_spool)
    ).telemetry_snapshot(sampled_at=sampled_at)
    surfaces: list[AcquisitionTelemetrySurface] = []
    for source_id in source_ids:
        try:
            source = telemetry.get(source_id)
        except LookupError:
            continue
        surfaces.append(AcquisitionTelemetrySurface(source=source, spool=spool))
    return tuple(surfaces)
