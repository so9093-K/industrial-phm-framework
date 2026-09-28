"""Small, explicit semantic bindings; channel identity remains independent."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MeasurementDefinition:
    property_name: str
    scope: str | None = None
    statistic: str | None = None
    unit: str | None = None
    unit_evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.property_name.strip():
            raise ValueError("property_name must not be empty")
        if (self.unit is None) != (self.unit_evidence is None):
            raise ValueError("known units require evidence; unknown units have no evidence")
        for value in (self.scope, self.statistic, self.unit, self.unit_evidence):
            if value is not None and not value.strip():
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
