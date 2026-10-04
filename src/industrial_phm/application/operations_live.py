"""Bounded live-observation projection for the Operations signal workspace."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from industrial_phm.application.acquisition_telemetry import AcquisitionTelemetrySurface
from industrial_phm.application.measurement_history import (
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
)
from industrial_phm.application.operations_assets import AssetWorkspaceSource
from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.source_registration import RegisteredSource, SourceType


@dataclass(frozen=True, slots=True)
class LiveObservationSeries:
    """One mapped live source/point for a selected asset channel."""

    source_id: str
    source_name: str
    measurement_point_id: str | None
    status: OperationsMonitorStatus
    last_received_at: datetime | None
    last_source_timestamp: datetime | None
    average_event_rate_hz: float | None
    latest_point: MeasurementHistoryPoint | None
    recent_points: tuple[MeasurementHistoryPoint, ...]

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.source_name, "source_name")
        if self.measurement_point_id is not None:
            _require_text(self.measurement_point_id, "measurement_point_id")
        if not isinstance(self.status, OperationsMonitorStatus):
            raise ValueError("status must be an OperationsMonitorStatus")
        for field_name in ("last_received_at", "last_source_timestamp"):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)
        if self.average_event_rate_hz is not None and self.average_event_rate_hz < 0:
            raise ValueError("average_event_rate_hz must not be negative")
        if self.latest_point is not None:
            _validate_point_identity(
                self.latest_point,
                source_id=self.source_id,
                measurement_point_id=self.measurement_point_id,
            )
        recent = tuple(self.recent_points)
        for point in recent:
            _validate_point_identity(
                point,
                source_id=self.source_id,
                measurement_point_id=self.measurement_point_id,
            )
        if recent != tuple(
            sorted(
                recent,
                key=lambda item: (
                    item.measurement.event_at is None,
                    (
                        0.0
                        if item.measurement.event_at is None
                        else item.measurement.event_at.timestamp()
                    ),
                    item.measurement.raw_evidence_id,
                ),
            )
        ):
            raise ValueError("recent_points must use deterministic event-time order")
        object.__setattr__(self, "recent_points", recent)


@dataclass(frozen=True, slots=True)
class LiveObservationView:
    """Current and recent evidence for one selected asset/channel."""

    asset_id: str
    channel_id: str
    sampled_at: datetime
    point_budget: int
    truncated: bool
    series: tuple[LiveObservationSeries, ...]

    def __post_init__(self) -> None:
        _require_text(self.asset_id, "asset_id")
        _require_text(self.channel_id, "channel_id")
        _require_aware(self.sampled_at, "sampled_at")
        if isinstance(self.point_budget, bool) or not isinstance(self.point_budget, int):
            raise ValueError("point_budget must be an integer")
        if self.point_budget < 1:
            raise ValueError("point_budget must be positive")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a bool")
        series = tuple(self.series)
        if series != tuple(
            sorted(
                series,
                key=lambda item: (item.source_id, item.measurement_point_id or ""),
            )
        ):
            raise ValueError("series must use source/measurement-point order")
        object.__setattr__(self, "series", series)

    @property
    def latest_received_at(self) -> datetime | None:
        return max(
            (item.last_received_at for item in self.series if item.last_received_at is not None),
            default=None,
        )


def build_live_observation_view(
    *,
    asset_id: str,
    channel_id: str,
    registered_sources: Sequence[RegisteredSource],
    asset_sources: Sequence[AssetWorkspaceSource],
    acquisition_surfaces: Sequence[AcquisitionTelemetrySurface],
    latest_points: Sequence[MeasurementHistoryPoint],
    recent_page: MeasurementHistoryPage,
    sampled_at: datetime,
) -> LiveObservationView:
    """Project one channel without creating a second live-data source of truth."""

    _require_text(asset_id, "asset_id")
    _require_text(channel_id, "channel_id")
    _require_aware(sampled_at, "sampled_at")

    registered = tuple(registered_sources)
    workspace_sources = tuple(asset_sources)
    surfaces = tuple(acquisition_surfaces)
    latest = tuple(latest_points)

    if any(not isinstance(source, RegisteredSource) for source in registered):
        raise ValueError("registered_sources contains an unsupported value")
    if any(not isinstance(source, AssetWorkspaceSource) for source in workspace_sources):
        raise ValueError("asset_sources contains an unsupported value")
    if any(not isinstance(surface, AcquisitionTelemetrySurface) for surface in surfaces):
        raise ValueError("acquisition_surfaces contains an unsupported value")
    if any(not isinstance(point, MeasurementHistoryPoint) for point in latest):
        raise ValueError("latest_points contains an unsupported value")
    if not isinstance(recent_page, MeasurementHistoryPage):
        raise ValueError("recent_page must be a MeasurementHistoryPage")

    mapped_sources = tuple(
        sorted(
            (
                source
                for source in registered
                if source.asset_id == asset_id
                and source.source_type == SourceType.OPCUA
                and any(identity.channel_id == channel_id for identity in source.channel_identities)
            ),
            key=lambda source: source.source_id,
        )
    )
    workspace_by_source = {source.source_id: source for source in workspace_sources}
    surface_by_source = {surface.source.source_id: surface for surface in surfaces}
    if len(surface_by_source) != len(surfaces):
        raise ValueError("acquisition_surfaces must contain unique source ids")

    for point in (*latest, *recent_page.points):
        measurement = point.measurement
        if measurement.asset_id != asset_id or measurement.channel_id != channel_id:
            raise ValueError("measurement points must match asset_id and channel_id")

    series: list[LiveObservationSeries] = []
    for source in mapped_sources:
        workspace_source = workspace_by_source.get(source.source_id)
        if workspace_source is None:
            raise ValueError("mapped live source must exist in asset_sources")
        point_id = source.measurement_point_id
        source_latest = next(
            (
                point
                for point in latest
                if point.measurement.source_id == source.source_id
                and point.measurement.measurement_point_id == point_id
            ),
            None,
        )
        source_recent = tuple(
            point
            for point in recent_page.points
            if point.measurement.source_id == source.source_id
            and point.measurement.measurement_point_id == point_id
        )
        surface = surface_by_source.get(source.source_id)
        flow = None if surface is None else surface.source.flow
        last_receipt = None if surface is None else surface.source.last_receipt
        last_received_at = None if surface is None else surface.source.last_received_at
        last_source_timestamp = (
            flow.last_source_timestamp
            if flow is not None and flow.last_source_timestamp is not None
            else None if last_receipt is None else last_receipt.source_timestamp
        )
        event_rate = None if flow is None else flow.average_event_rate_hz(as_of=sampled_at)
        series.append(
            LiveObservationSeries(
                source_id=source.source_id,
                source_name=source.name,
                measurement_point_id=point_id,
                status=workspace_source.status,
                last_received_at=last_received_at,
                last_source_timestamp=last_source_timestamp,
                average_event_rate_hz=event_rate,
                latest_point=source_latest,
                recent_points=source_recent,
            )
        )

    return LiveObservationView(
        asset_id=asset_id,
        channel_id=channel_id,
        sampled_at=sampled_at,
        point_budget=recent_page.point_budget,
        truncated=recent_page.truncated,
        series=tuple(series),
    )


def _validate_point_identity(
    point: MeasurementHistoryPoint,
    *,
    source_id: str,
    measurement_point_id: str | None,
) -> None:
    if not isinstance(point, MeasurementHistoryPoint):
        raise ValueError("point must be a MeasurementHistoryPoint")
    measurement = point.measurement
    if (
        measurement.source_id != source_id
        or measurement.measurement_point_id != measurement_point_id
    ):
        raise ValueError("point identity must match its live observation series")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
