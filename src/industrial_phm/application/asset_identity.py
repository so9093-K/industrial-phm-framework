"""First-class physical asset identity contracts for operational application flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssetIdentity:
    """Stable identity for one physical asset without source or health semantics."""

    asset_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.asset_id, "asset_id")


@dataclass(frozen=True, slots=True)
class ComponentIdentity:
    """Identity for one component within a physical asset."""

    asset_id: str
    component_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.component_id, "component_id")

    @property
    def asset(self) -> AssetIdentity:
        """Return the owning physical asset identity."""
        return AssetIdentity(self.asset_id)


@dataclass(frozen=True, slots=True)
class MeasurementPointIdentity:
    """Identity for one measurement point on an asset or optional component."""

    asset_id: str
    measurement_point_id: str
    component_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if self.component_id is not None:
            _validate_identifier(self.component_id, "component_id")

    @property
    def asset(self) -> AssetIdentity:
        """Return the owning physical asset identity."""
        return AssetIdentity(self.asset_id)

    @property
    def component(self) -> ComponentIdentity | None:
        """Return the optional owning component identity."""
        if self.component_id is None:
            return None
        return ComponentIdentity(
            asset_id=self.asset_id,
            component_id=self.component_id,
        )


@dataclass(frozen=True, slots=True)
class ChannelIdentity:
    """Identity for one observed channel within an asset context.

    Current source contracts may omit measurement-point and component identity. The
    channel therefore preserves those scopes only when they are explicitly available;
    it never invents a hierarchy from a channel name.
    """

    asset_id: str
    channel_id: str
    measurement_point_id: str | None = None
    component_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.channel_id, "channel_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if self.component_id is not None:
            _validate_identifier(self.component_id, "component_id")

    @property
    def asset(self) -> AssetIdentity:
        """Return the owning physical asset identity."""
        return AssetIdentity(self.asset_id)

    @property
    def component(self) -> ComponentIdentity | None:
        """Return the optional component identity."""
        if self.component_id is None:
            return None
        return ComponentIdentity(
            asset_id=self.asset_id,
            component_id=self.component_id,
        )

    @property
    def measurement_point(self) -> MeasurementPointIdentity | None:
        """Return the optional measurement-point identity."""
        if self.measurement_point_id is None:
            return None
        return MeasurementPointIdentity(
            asset_id=self.asset_id,
            measurement_point_id=self.measurement_point_id,
            component_id=self.component_id,
        )


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
