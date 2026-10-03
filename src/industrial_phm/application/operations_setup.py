"""Setup workspace projections for Operations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from industrial_phm.application.collection_control import (
    CollectionControlRecord,
    CollectionDesiredState,
)
from industrial_phm.application.measurement_semantics import ChannelSemanticBinding
from industrial_phm.application.source_freshness import SourceFreshnessPolicy
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleState,
)
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceType,
)


@dataclass(frozen=True, slots=True)
class SetupSignalView:
    channel_id: str
    source_locator: str
    observed_property: str | None
    scope: str | None
    statistic: str | None
    unit: str | None
    semantic_version: str | None
    interpretation_evidence: str | None

    def __post_init__(self) -> None:
        _require_text(self.channel_id, "channel_id")
        _require_text(self.source_locator, "source_locator")
        for field_name in (
            "observed_property",
            "scope",
            "statistic",
            "unit",
            "semantic_version",
            "interpretation_evidence",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_text(value, field_name)

    @property
    def meaning_defined(self) -> bool:
        return any(
            value is not None
            for value in (
                self.observed_property,
                self.scope,
                self.statistic,
                self.unit,
            )
        )


@dataclass(frozen=True, slots=True)
class SetupSourceView:
    source_id: str
    name: str
    source_type: SourceType
    asset_id: str
    measurement_point_id: str | None
    lifecycle_state: SourceLifecycleState
    registered_at: datetime
    connection_target: str
    collection_desired_state: CollectionDesiredState | None
    collection_requested_at: datetime | None
    freshness_max_age_seconds: float | None
    freshness_changed_at: datetime | None
    signals: Sequence[SetupSignalView]

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.source_id, "source_id"),
            (self.name, "name"),
            (self.asset_id, "asset_id"),
            (self.connection_target, "connection_target"),
        ):
            _require_text(value, field_name)
        if not isinstance(self.source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        if self.measurement_point_id is not None:
            _require_text(self.measurement_point_id, "measurement_point_id")
        if not isinstance(self.lifecycle_state, SourceLifecycleState):
            raise ValueError("lifecycle_state must be a SourceLifecycleState")
        _require_aware(self.registered_at, "registered_at")
        if self.collection_desired_state is not None and not isinstance(
            self.collection_desired_state,
            CollectionDesiredState,
        ):
            raise ValueError("collection_desired_state must be CollectionDesiredState or None")
        if self.collection_requested_at is not None:
            _require_aware(self.collection_requested_at, "collection_requested_at")
        if (self.collection_desired_state is None) != (self.collection_requested_at is None):
            raise ValueError("collection state and requested time must be recorded together")
        if self.freshness_max_age_seconds is not None and self.freshness_max_age_seconds <= 0:
            raise ValueError("freshness_max_age_seconds must be positive when provided")
        if (self.freshness_max_age_seconds is None) != (self.freshness_changed_at is None):
            raise ValueError("freshness policy age and changed time must be recorded together")
        if self.freshness_changed_at is not None:
            _require_aware(self.freshness_changed_at, "freshness_changed_at")
        signals = tuple(self.signals)
        if any(not isinstance(item, SetupSignalView) for item in signals):
            raise ValueError("signals must contain SetupSignalView values")
        if tuple(sorted(item.channel_id for item in signals)) != tuple(
            item.channel_id for item in signals
        ):
            raise ValueError("signals must use channel-id order")
        object.__setattr__(self, "signals", signals)

    @property
    def semantic_coverage(self) -> tuple[int, int]:
        return sum(item.meaning_defined for item in self.signals), len(self.signals)


@dataclass(frozen=True, slots=True)
class SetupWorkspaceView:
    sources: Sequence[SetupSourceView]

    def __post_init__(self) -> None:
        sources = tuple(self.sources)
        if any(not isinstance(item, SetupSourceView) for item in sources):
            raise ValueError("sources must contain SetupSourceView values")
        if tuple(sorted(item.source_id for item in sources)) != tuple(
            item.source_id for item in sources
        ):
            raise ValueError("sources must use source-id order")
        object.__setattr__(self, "sources", sources)


def build_setup_workspace(
    *,
    sources: Sequence[RegisteredSource],
    lifecycle_records: Sequence[SourceLifecycleRecord],
    collection_records: Sequence[CollectionControlRecord] = (),
    freshness_policies: Sequence[SourceFreshnessPolicy] = (),
) -> SetupWorkspaceView:
    """Project registered source configuration without runtime-health inference."""

    source_values = tuple(sources)
    lifecycle_values = tuple(lifecycle_records)
    collection_values = tuple(collection_records)
    freshness_values = tuple(freshness_policies)

    if any(not isinstance(item, RegisteredSource) for item in source_values):
        raise ValueError("sources must contain RegisteredSource values")
    if any(not isinstance(item, SourceLifecycleRecord) for item in lifecycle_values):
        raise ValueError("lifecycle_records must contain SourceLifecycleRecord values")
    if any(not isinstance(item, CollectionControlRecord) for item in collection_values):
        raise ValueError("collection_records must contain CollectionControlRecord values")
    if any(not isinstance(item, SourceFreshnessPolicy) for item in freshness_values):
        raise ValueError("freshness_policies must contain SourceFreshnessPolicy values")

    source_ids = tuple(item.source_id for item in source_values)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("sources must use unique source ids")

    lifecycle_by_source = {item.source_id: item for item in lifecycle_values}
    if set(lifecycle_by_source) != set(source_ids):
        raise ValueError("lifecycle_records must exactly match registered sources")

    collection_by_source = {item.source_id: item for item in collection_values}
    if len(collection_by_source) != len(collection_values):
        raise ValueError("collection_records must use unique source ids")
    unexpected_collection = sorted(set(collection_by_source) - set(source_ids))
    if unexpected_collection:
        raise ValueError(
            "collection_records reference unregistered sources: " + ", ".join(unexpected_collection)
        )

    freshness_by_source = {item.source_id: item for item in freshness_values}
    if len(freshness_by_source) != len(freshness_values):
        raise ValueError("freshness_policies must use unique source ids")
    unexpected_freshness = sorted(set(freshness_by_source) - set(source_ids))
    if unexpected_freshness:
        raise ValueError(
            "freshness_policies reference unregistered sources: " + ", ".join(unexpected_freshness)
        )

    projected = tuple(
        sorted(
            (
                _project_source(
                    source,
                    lifecycle_by_source[source.source_id],
                    collection_by_source.get(source.source_id),
                    freshness_by_source.get(source.source_id),
                )
                for source in source_values
            ),
            key=lambda item: item.source_id,
        )
    )
    return SetupWorkspaceView(projected)


def _project_source(
    source: RegisteredSource,
    lifecycle: SourceLifecycleRecord,
    collection: CollectionControlRecord | None,
    freshness: SourceFreshnessPolicy | None,
) -> SetupSourceView:
    if source.source_id != lifecycle.source_id:
        raise ValueError("source and lifecycle identities must match")
    if collection is not None and collection.source_id != source.source_id:
        raise ValueError("source and collection identities must match")
    if freshness is not None and freshness.source_id != source.source_id:
        raise ValueError("source and freshness identities must match")

    config = source.config
    if isinstance(config, FileSourceConfig):
        signals = tuple(
            SetupSignalView(
                channel_id=channel_id,
                source_locator=channel_id,
                observed_property=None,
                scope=None,
                statistic=None,
                unit=None,
                semantic_version=None,
                interpretation_evidence=None,
            )
            for channel_id in sorted(config.channel_columns)
        )
        connection_target = config.source_path
    elif isinstance(config, OpcUaSourceConfig):
        binding_by_channel = {binding.channel_id: binding for binding in config.semantic_bindings}
        signals = tuple(
            _opcua_signal(
                mapping.channel_id,
                mapping.node_id,
                binding_by_channel.get(mapping.channel_id),
            )
            for mapping in sorted(config.node_mappings, key=lambda item: item.channel_id)
        )
        connection_target = config.endpoint_url
    else:  # pragma: no cover - RegisteredSource already enforces supported config types
        raise ValueError("unsupported source config")

    return SetupSourceView(
        source_id=source.source_id,
        name=source.name,
        source_type=source.source_type,
        asset_id=source.asset_id,
        measurement_point_id=source.measurement_point_id,
        lifecycle_state=lifecycle.state,
        registered_at=source.registered_at,
        connection_target=connection_target,
        collection_desired_state=(None if collection is None else collection.desired_state),
        collection_requested_at=None if collection is None else collection.requested_at,
        freshness_max_age_seconds=(
            None if freshness is None else freshness.max_observation_age_seconds
        ),
        freshness_changed_at=None if freshness is None else freshness.changed_at,
        signals=signals,
    )


def _opcua_signal(
    channel_id: str,
    node_id: str,
    binding: ChannelSemanticBinding | None,
) -> SetupSignalView:
    definition = None if binding is None else binding.definition
    return SetupSignalView(
        channel_id=channel_id,
        source_locator=node_id,
        observed_property=(None if definition is None else definition.observed_property),
        scope=None if definition is None else definition.scope,
        statistic=None if definition is None else definition.statistic,
        unit=None if definition is None else definition.unit,
        semantic_version=None if binding is None else binding.version,
        interpretation_evidence=(None if binding is None else binding.interpretation_evidence),
    )


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
