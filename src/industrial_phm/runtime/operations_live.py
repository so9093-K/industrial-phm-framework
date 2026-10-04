"""Bounded concrete reads for the Operations live-signal surface."""

from __future__ import annotations

from collections.abc import Sequence
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
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.acquisition_spool import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
)
from industrial_phm.runtime.acquisition_telemetry import SqliteAcquisitionTelemetryRepository
from industrial_phm.runtime.operations_app_wiring import OperationsAppPaths


def load_operations_live_observation(
    paths: OperationsAppPaths,
    *,
    asset_id: str,
    channel_id: str,
    registered_sources: Sequence[RegisteredSource],
    asset_sources: Sequence[AssetWorkspaceSource],
    sampled_at: datetime,
    lookback_seconds: float = 60.0,
    point_budget: int = 600,
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
        latest_points = history.query_latest_measurements(asset_id, channel_id=channel_id)
        event_times = tuple(
            point.measurement.event_at
            for point in latest_points
            if point.measurement.event_at is not None
        )
        if event_times:
            end_at = max(event_times) + timedelta(microseconds=1)
            recent_page = history.query_measurement_page(
                asset_id,
                channel_id=channel_id,
                start_at=end_at - timedelta(seconds=float(lookback_seconds)),
                end_at=end_at,
                point_budget=point_budget,
                latest=True,
            )

    surfaces = _load_live_acquisition_surfaces(
        paths,
        source_ids=mapped_source_ids,
        sampled_at=sampled_at,
    )
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
