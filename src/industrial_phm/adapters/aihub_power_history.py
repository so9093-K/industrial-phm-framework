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

# Version rule: every observation stores its semantic binding immutably. Any change
# to what decides meaning (channel membership, property, scope, statistic, unit,
# unit evidence, member exceptions and their reasons, or the profiled archive scope)
# is a new version; a published version is never edited. Generic explanatory wording
# written into interpretation_evidence is serialization, not dictionary payload.
# Pinned digests make an accidental in-place edit fail the contract test. History
# metadata v3 writes semantics-v1, v4 writes semantics-v2 and v5 writes semantics-v3.
AIHUB_239_SEMANTICS_V1 = "aihub-239-semantics-v1"
AIHUB_239_SEMANTICS_V2 = "aihub-239-semantics-v2"
AIHUB_239_SEMANTICS_V3 = "aihub-239-semantics-v3"
AIHUB_239_SEMANTICS_DIGESTS = {
    AIHUB_239_SEMANTICS_V1: "a90327d6d885480ca7b044dc704fb95aa14677b8713f75a4d9401b80178a054d",
    AIHUB_239_SEMANTICS_V2: "4cc29be9d2fc98e7f4531e0504414a848329794ac049c78b3d097fda7da0db7c",
    AIHUB_239_SEMANTICS_V3: "2df8cf5bfaeab39f22396ab1dc849db23483c4c4676d8515139b6a10c4d130b1",
}
_SCHEMA_SEMANTICS = {
    "v3": AIHUB_239_SEMANTICS_V1,
    "v4": AIHUB_239_SEMANTICS_V2,
    "v5": AIHUB_239_SEMANTICS_V3,
}
# Earlier schemas stay accepted only for exact retry of imports that used them.
AIHUB_239_HISTORY_SCHEMAS = ("v1", "v2", "v3", "v4", "v5")
AIHUB_239_DEFAULT_HISTORY_SCHEMA = "v5"
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


_BOILER_SHA256 = "87ad1f77172f549c5aa5f78a857ddd8b02cb010a08af67ea64a3cf4c5a824023"
_EXTRUDER_SHA256 = "7fd3a50f1222a695fc440ef2d4e8f2b431dd419b2249b60a6bc0ab34d5472a17"
_VOLTAGES = frozenset({"R상전압", "S상전압", "T상전압", "상전압평균", "선간전압평균"})
_CURRENTS = frozenset({"R상전류", "S상전류", "T상전류", "전류평균"})
# semantics-v2 keeps the v1 definitions but leaves channels unresolved in members
# where a supporting relation median falls outside its tolerance in the full-archive
# relation profile (tools/aihub/relation_profile.py). Reasons are part of the payload.
_V2_MEMBER_EXCEPTIONS: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    (_BOILER_SHA256, "5.보일러/SourceData_364.json"): (
        _VOLTAGES,
        "line/phase voltage median 1.666, outside sqrt(3) +-2%",
    ),
    (_EXTRUDER_SHA256, "7.압출기/SourceData_214.json"): (
        frozenset({"선간전압평균"}),
        "선간전압평균 / mean(R,S,T상선간전압) median 1.734, outside 1 +-1%",
    ),
    (_EXTRUDER_SHA256, "7.압출기/SourceData_385.json"): (
        frozenset({"선간전압평균"}),
        "선간전압평균 / mean(R,S,T상선간전압) median 1.735, outside 1 +-1%",
    ),
    (_EXTRUDER_SHA256, "7.압출기/SourceData_130.json"): (
        _CURRENTS,
        "sqrt(P^2+Q^2) / (V*I) median 0.0625, outside 1 +-5%",
    ),
}


_COMPRESSOR_SHA256 = "ffde668bfab1d669fa7dc649fdcc9aaee30305af61c732852377c10818043119"
_LINE_VOLTAGE_MEAN = frozenset({"선간전압평균"})


def _line_mean_reason(median: str) -> str:
    return f"선간전압평균 / mean(R,S,T상선간전압) median {median}, outside 1 +-1%"


# semantics-v3 applies definitions only to archives inside its profiled evidence
# scope: every member went through the full-archive source profile and relation
# profile (tools/aihub/profile.py, relation_profile.py). Any other archive keeps
# its raw values but every canonical meaning stays unresolved (fail-closed).
_V3_PROFILED_ARCHIVES: dict[str, str] = {
    _BOILER_SHA256: "AI-Hub 239 Training/raw 5.보일러.zip (filekey 44033)",
    _EXTRUDER_SHA256: "AI-Hub 239 Training/raw 7.압출기.zip (filekey 44035)",
    _COMPRESSOR_SHA256: "AI-Hub 239 Training/raw 3.공기압축기.zip (filekey 44031)",
}
_V3_MEMBER_EXCEPTIONS: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    **_V2_MEMBER_EXCEPTIONS,
    (_COMPRESSOR_SHA256, "3.공기압축기/SourceData_135.json"): (
        _LINE_VOLTAGE_MEAN | _CURRENTS,
        _line_mean_reason("1.732") + "; sqrt(P^2+Q^2) / (V*I) median 1.143, outside 1 +-5%",
    ),
    **{
        (_COMPRESSOR_SHA256, f"3.공기압축기/SourceData_{number}.json"): (
            _LINE_VOLTAGE_MEAN,
            _line_mean_reason(median),
        )
        for number, median in (
            ("34", "1.726"),
            ("38", "1.738"),
            ("44", "1.737"),
            ("48", "1.736"),
            ("76", "1.732"),
            ("137", "1.732"),
            ("138", "1.732"),
            ("232", "1.736"),
            ("233", "1.740"),
            ("336", "1.731"),
            ("337", "1.731"),
            ("338", "1.734"),
            ("339", "1.731"),
        )
    },
}
_MEMBER_EXCEPTIONS = {
    AIHUB_239_SEMANTICS_V2: _V2_MEMBER_EXCEPTIONS,
    AIHUB_239_SEMANTICS_V3: _V3_MEMBER_EXCEPTIONS,
}


def _exception_payload(
    exceptions: dict[tuple[str, str], tuple[frozenset[str], str]],
) -> list[list[object]]:
    return [
        [archive, member, sorted(channels), reason]
        for (archive, member), (channels, reason) in sorted(exceptions.items())
    ]


def semantics_dictionary_digest(version: str) -> str:
    """SHA-256 of the canonical dictionary payload of one semantics version."""
    definitions = {name: asdict(d) for name, d in _CONFIRMED_DEFINITIONS.items()}
    payload: object
    if version == AIHUB_239_SEMANTICS_V1:
        payload = definitions
    elif version == AIHUB_239_SEMANTICS_V2:
        payload = {
            "definitions": definitions,
            "member_exceptions": _exception_payload(_V2_MEMBER_EXCEPTIONS),
        }
    elif version == AIHUB_239_SEMANTICS_V3:
        # Scope membership decides meaning, so the SHA-256 set is part of the payload;
        # the archive descriptions are documentation and stay out of it.
        payload = {
            "definitions": definitions,
            "member_exceptions": _exception_payload(_V3_MEMBER_EXCEPTIONS),
            "profiled_archives": sorted(_V3_PROFILED_ARCHIVES),
        }
    else:
        raise ValueError(f"unknown AI-Hub 239 semantics version: {version}")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ChannelInterpretation:
    """A channel definition and, when unresolved, why the evidence does not apply."""

    definition: MeasurementDefinition
    unresolved_reason: str | None = None


def interpret_channel(
    version: str, channel_name: str, *, archive_sha256: str, member: str
) -> ChannelInterpretation:
    """Return the evidenced definition, or an unresolved one with its reason."""
    if version not in AIHUB_239_SEMANTICS_DIGESTS:
        raise ValueError(f"unknown AI-Hub 239 semantics version: {version}")
    if version == AIHUB_239_SEMANTICS_V3 and archive_sha256 not in _V3_PROFILED_ARCHIVES:
        return ChannelInterpretation(
            MeasurementDefinition(),
            f"archive sha256 is outside the {version} profiled evidence scope",
        )
    channels, reason = _MEMBER_EXCEPTIONS.get(version, {}).get(
        (archive_sha256, member), (frozenset(), "")
    )
    if channel_name in channels:
        return ChannelInterpretation(
            MeasurementDefinition(), f"{version} member exception: {reason}"
        )
    definition = _CONFIRMED_DEFINITIONS.get(channel_name)
    if definition is None:
        return ChannelInterpretation(
            MeasurementDefinition(),
            f"no evidenced canonical definition is published for this ITEM_NAME in {version}",
        )
    return ChannelInterpretation(definition)


def channel_definition(
    version: str, channel_name: str, *, archive_sha256: str, member: str
) -> MeasurementDefinition:
    """Return the evidenced definition, or an unresolved one where evidence is absent."""
    return interpret_channel(
        version, channel_name, archive_sha256=archive_sha256, member=member
    ).definition


def history_schema_semantics(metadata_schema: str) -> str | None:
    """Return the semantics version a history metadata schema writes, if any."""
    if metadata_schema not in AIHUB_239_HISTORY_SCHEMAS:
        raise ValueError(f"metadata_schema must be one of {', '.join(AIHUB_239_HISTORY_SCHEMAS)}")
    return _SCHEMA_SEMANTICS.get(metadata_schema)


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
    metadata_schema: str = AIHUB_239_DEFAULT_HISTORY_SCHEMA,
) -> FileBackfillEvent:
    semantics_version = history_schema_semantics(metadata_schema)
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
    # v1/v2 assert only the source's name; v3+ apply an evidenced dictionary.
    # Earlier schemas remain available for exact retry; channel identity is unchanged.
    interpretation = (
        interpret_channel(
            semantics_version,
            record.channel_name,
            archive_sha256=archive_digest,
            member=record.member,
        )
        if semantics_version is not None
        else ChannelInterpretation(MeasurementDefinition())
    )
    definition = interpretation.definition
    unresolved_evidence = "source ITEM_NAME; canonical property and unit unresolved"
    if metadata_schema == "v5" and interpretation.unresolved_reason is not None:
        # v5 records why a meaning is unresolved; v1-v4 keep their exact text for retry.
        unresolved_evidence += f": {interpretation.unresolved_reason}"
    semantic = ChannelSemanticBinding(
        source_id=binding.source_id,
        channel_id=record.channel_name,
        version=semantics_version or binding.version,
        definition=definition,
        interpretation_evidence=(
            "source ITEM_NAME; provider unit table and observed data agree; "
            "temporal aggregation within the 1-minute sample unresolved"
            if definition.unit is not None
            else unresolved_evidence
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
