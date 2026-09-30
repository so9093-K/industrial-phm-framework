"""Explicit registration input for OPC UA channel semantics.

This parser is intentionally small and literal. It converts user-provided CSV rows
into versioned ChannelSemanticBinding values and never derives physical meaning from
channel IDs, browse names or NodeIds.
"""

from __future__ import annotations

import csv
from io import StringIO

from industrial_phm.application.measurement_semantics import (
    ChannelSemanticBinding,
    MeasurementDefinition,
)

OPCUA_SEMANTIC_BINDING_INPUT_COLUMNS = (
    "channel_id",
    "observed_property",
    "scope",
    "statistic",
    "unit",
    "unit_evidence",
    "semantic_version",
    "interpretation_evidence",
)


def parse_opcua_semantic_bindings(
    value: str,
    *,
    source_id: str,
) -> tuple[ChannelSemanticBinding, ...]:
    """Parse explicit CSV rows into source-scoped semantic bindings.

    Each non-empty row must contain exactly the columns in
    OPCUA_SEMANTIC_BINDING_INPUT_COLUMNS. CSV quoting is supported, so evidence
    text may contain commas. Optional semantic fields stay None when left blank.
    No value is inferred from channel identity.
    """
    if not isinstance(value, str):
        raise ValueError("semantic binding input must be a string")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must not be empty")
    if source_id != source_id.strip():
        raise ValueError("source_id must not contain surrounding whitespace")

    bindings: list[ChannelSemanticBinding] = []
    seen_channels: set[str] = set()
    reader = csv.reader(StringIO(value))
    expected = len(OPCUA_SEMANTIC_BINDING_INPUT_COLUMNS)

    for line_number, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) != expected:
            raise ValueError(
                "OPC UA semantic binding line "
                f"{line_number} must contain {expected} CSV fields: "
                + ",".join(OPCUA_SEMANTIC_BINDING_INPUT_COLUMNS)
            )

        (
            channel_id,
            observed_property,
            scope,
            statistic,
            unit,
            unit_evidence,
            semantic_version,
            interpretation_evidence,
        ) = (cell.strip() for cell in row)

        if not channel_id:
            raise ValueError(f"OPC UA semantic binding line {line_number} requires channel_id")
        if channel_id in seen_channels:
            raise ValueError(f"OPC UA semantic binding channel is duplicated: {channel_id}")
        seen_channels.add(channel_id)

        def optional(text: str) -> str | None:
            return text or None

        bindings.append(
            ChannelSemanticBinding(
                source_id=source_id,
                channel_id=channel_id,
                version=semantic_version,
                definition=MeasurementDefinition(
                    observed_property=optional(observed_property),
                    scope=optional(scope),
                    statistic=optional(statistic),
                    unit=optional(unit),
                    unit_evidence=optional(unit_evidence),
                ),
                interpretation_evidence=interpretation_evidence,
            )
        )

    return tuple(bindings)
