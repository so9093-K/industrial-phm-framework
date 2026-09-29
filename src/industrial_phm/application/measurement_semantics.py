"""Small, explicit semantic bindings; channel identity remains independent."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MeasurementDefinition:
    observed_property: str | None = None
    scope: str | None = None
    statistic: str | None = None
    unit: str | None = None
    unit_evidence: str | None = None

    def __post_init__(self) -> None:
        if (self.unit is None) != (self.unit_evidence is None):
            raise ValueError("known units require evidence; unknown units have no evidence")
        for value in (
            self.observed_property,
            self.scope,
            self.statistic,
            self.unit,
            self.unit_evidence,
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("provided semantics must not be empty")


@dataclass(frozen=True, slots=True)
class ChannelSemanticBinding:
    """A versioned source-specific interpretation, not a physical identity rule.

    Bindings are persisted with each imported observation. Future mapping changes
    cannot reinterpret old history silently; validity is that observation's scope.
    """

    source_id: str
    channel_id: str
    version: str
    definition: MeasurementDefinition
    interpretation_evidence: str

    def __post_init__(self) -> None:
        if not all(
            s.strip()
            for s in (self.source_id, self.channel_id, self.version, self.interpretation_evidence)
        ):
            raise ValueError("binding identity, version and evidence must not be empty")
        if not isinstance(self.definition, MeasurementDefinition):
            raise ValueError("definition must be MeasurementDefinition")


_SEMANTIC_DEFINITION_KEYS = frozenset(
    {"observed_property", "scope", "statistic", "unit", "unit_evidence"}
)
_SEMANTIC_BINDING_KEYS = frozenset(
    {"source_id", "channel_id", "version", "definition", "interpretation_evidence"}
)


def serialize_channel_semantic_binding(binding: ChannelSemanticBinding) -> dict[str, object]:
    """Serialize one exact binding snapshot for durable operational provenance."""
    if not isinstance(binding, ChannelSemanticBinding):
        raise ValueError("binding must be a ChannelSemanticBinding")
    definition = binding.definition
    return {
        "source_id": binding.source_id,
        "channel_id": binding.channel_id,
        "version": binding.version,
        "definition": {
            "observed_property": definition.observed_property,
            "scope": definition.scope,
            "statistic": definition.statistic,
            "unit": definition.unit,
            "unit_evidence": definition.unit_evidence,
        },
        "interpretation_evidence": binding.interpretation_evidence,
    }


def parse_channel_semantic_binding(value: object) -> ChannelSemanticBinding:
    """Parse a durable binding snapshot without inferring omitted semantics."""
    if not isinstance(value, dict):
        raise ValueError("semantic binding must be an object")
    if frozenset(value) != _SEMANTIC_BINDING_KEYS:
        raise ValueError("semantic binding keys do not match schema")
    definition_raw = value["definition"]
    if not isinstance(definition_raw, dict):
        raise ValueError("semantic binding definition must be an object")
    if frozenset(definition_raw) != _SEMANTIC_DEFINITION_KEYS:
        raise ValueError("semantic definition keys do not match schema")

    def optional_text(raw: object, field_name: str) -> str | None:
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ValueError(f"{field_name} must be a string or null")
        return raw

    def required_text(raw: object, field_name: str) -> str:
        if not isinstance(raw, str):
            raise ValueError(f"{field_name} must be a string")
        return raw

    return ChannelSemanticBinding(
        source_id=required_text(value["source_id"], "source_id"),
        channel_id=required_text(value["channel_id"], "channel_id"),
        version=required_text(value["version"], "version"),
        definition=MeasurementDefinition(
            observed_property=optional_text(
                definition_raw["observed_property"], "observed_property"
            ),
            scope=optional_text(definition_raw["scope"], "scope"),
            statistic=optional_text(definition_raw["statistic"], "statistic"),
            unit=optional_text(definition_raw["unit"], "unit"),
            unit_evidence=optional_text(definition_raw["unit_evidence"], "unit_evidence"),
        ),
        interpretation_evidence=required_text(
            value["interpretation_evidence"], "interpretation_evidence"
        ),
    )
