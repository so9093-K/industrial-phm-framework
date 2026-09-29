"""Explicit AI-Hub source-to-history binding; no implicit asset/unit/time guesses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from industrial_phm.adapters.aihub_power import PowerObservation
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.application.measurement_semantics import (
    ChannelSemanticBinding,
    MeasurementDefinition,
)

AIHUB_239_SEMANTICS_VERSION = "aihub-239-semantics-v1"
_GUIDE = (
    "AI-Hub 239 construction/usage guideline v1.5 section 1.6.3 unit table "
    "(sha256 dfad9cd6d9451f571048813ae394923faec165519cc6eab84babee9c2f66560a)"
)
_PHASE_MEAN = "arithmetic mean of phases R, S and T"
# Only items where the provider document and observed data agree. Power, power
# factor and energy contradict their documented units in the data and stay
# unresolved; see docs/research/aihub-239-source-profile.md.
_CONFIRMED_DEFINITIONS: dict[str, MeasurementDefinition] = {
    "주파수": MeasurementDefinition(
        "frequency",
        scope="three-phase supply voltage",
        unit="Hz",
        unit_evidence=f"{_GUIDE}; observed values near the 60 Hz grid",
    ),
    **{
        f"{phase}상전압": MeasurementDefinition(
            "phase voltage",
            scope=f"phase {phase}",
            unit="V",
            unit_evidence=f"{_GUIDE}; line/phase voltage ratio about sqrt(3)",
        )
        for phase in "RST"
    },
    "상전압평균": MeasurementDefinition(
        "phase voltage",
        scope="three-phase",
        statistic=_PHASE_MEAN,
        unit="V",
        unit_evidence=f"{_GUIDE}; equals the mean of observed phase voltages",
    ),
    "선간전압평균": MeasurementDefinition(
        "line-to-line voltage",
        scope="three-phase",
        statistic="arithmetic mean of the three line-to-line pairs",
        unit="V",
        unit_evidence=f"{_GUIDE}; about sqrt(3) times the mean phase voltage",
    ),
    **{
        f"{phase}상전류": MeasurementDefinition(
            "phase current",
            scope=f"phase {phase}",
            unit="A",
            unit_evidence=f"{_GUIDE}; sqrt(P^2+Q^2) equals V*I per phase",
        )
        for phase in "RST"
    },
    "전류평균": MeasurementDefinition(
        "phase current",
        scope="three-phase",
        statistic=_PHASE_MEAN,
        unit="A",
        unit_evidence=f"{_GUIDE}; equals the mean of observed phase currents",
    ),
}


def confirmed_channel_definition(channel_name: str) -> MeasurementDefinition:
    """Return the evidenced definition, or an unresolved one for any other channel."""
    return _CONFIRMED_DEFINITIONS.get(channel_name, MeasurementDefinition())


@dataclass(frozen=True, slots=True)
class PowerHistoryBinding:
    source_id: str
    asset_id: str
    device_id: str
    device_board_id: str
    timezone: str
    identity_evidence: str
    timezone_evidence: str
    version: str

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be a nonempty string without surrounding whitespace")
        ZoneInfo(self.timezone)


def project_power_observation(
    record: PowerObservation,
    *,
    archive: Path,
    archive_digest: str,
    archive_bytes: int,
    binding: PowerHistoryBinding,
    metadata_schema: str = "v3",
) -> FileBackfillEvent:
    if metadata_schema not in {"v1", "v2", "v3"}:
        raise ValueError("metadata_schema must be v1, v2 or v3")
    if (record.device_id, record.device_board_id) != (binding.device_id, binding.device_board_id):
        raise ValueError("source device identifiers do not match the explicit asset binding")
    local = datetime.fromisoformat(record.timestamp_text)
    zone = ZoneInfo(binding.timezone)
    aware = local.replace(tzinfo=zone)
    if aware.utcoffset() != aware.replace(fold=1).utcoffset():
        raise ValueError(
            "ambiguous/nonexistent local time requires a separately resolved time policy"
        )
    if aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
        raise ValueError("nonexistent local source time")
    # v1/v2 assert only the source's name and remain available for exact retry.
    # v3 applies the evidenced dictionary; channel identity is unchanged.
    definition = (
        confirmed_channel_definition(record.channel_name)
        if metadata_schema == "v3"
        else MeasurementDefinition()
    )
    semantic = ChannelSemanticBinding(
        source_id=binding.source_id,
        channel_id=record.channel_name,
        version=AIHUB_239_SEMANTICS_VERSION if metadata_schema == "v3" else binding.version,
        definition=definition,
        interpretation_evidence=(
            "source ITEM_NAME; provider unit table and observed data agree; "
            "temporal aggregation within the 1-minute sample unresolved"
            if definition.unit is not None
            else "source ITEM_NAME; canonical property and unit unresolved"
        ),
    )
    semantic_metadata = asdict(semantic)
    if metadata_schema == "v1":
        # Exact legacy serialization for resuming an existing import. Readers must
        # not promote this source label to an interpreted observed property.
        semantic_metadata["definition"].pop("observed_property")
        semantic_metadata["definition"]["property_name"] = record.channel_name
    metadata = {
        "schema": f"aihub-239-history-{metadata_schema}",
        "archive_name": archive.name,
        "member": record.member,
        "record_index": record.record_index,
        "device_id": record.device_id,
        "device_board_id": record.device_board_id,
        "raw_timestamp": record.timestamp_text,
        "raw_record": json.loads(record.raw_record_json),
        "binding": asdict(binding),
        "semantics": semantic_metadata,
    }
    # The raw identity excludes mapping and selected range. Changing a binding
    # cannot silently insert a second copy of the same source observation.
    raw_identity = json.dumps(
        [binding.source_id, archive_digest, record.member, record.record_index],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return FileBackfillEvent(
        raw_evidence_id="aihub239:" + hashlib.sha256(raw_identity.encode()).hexdigest(),
        source_id=binding.source_id,
        asset_id=binding.asset_id,
        channel_id=record.channel_name,
        source_file=f"{archive.name}!/{record.member}",
        source_sha256=archive_digest,
        source_size_bytes=archive_bytes,
        sample_index=record.record_index,
        event_at=aware,
        value=record.value,
        source_metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )
