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
    metadata_schema: str = "v2",
) -> FileBackfillEvent:
    if metadata_schema not in {"v1", "v2"}:
        raise ValueError("metadata_schema must be v1 or v2")
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
    # Only the source's name is asserted here. A dictionary can later provide
    # evidenced property/phase/statistic mappings without changing identity.
    semantic = ChannelSemanticBinding(
        source_id=binding.source_id,
        channel_id=record.channel_name,
        version=binding.version,
        definition=MeasurementDefinition(),
        interpretation_evidence="source ITEM_NAME; canonical property and unit unresolved",
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
