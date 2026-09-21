"""Presentation-independent summary of recorded prognostics evidence.

This module formats nothing for a specific UI framework. It selects and labels values that a
user-facing surface must show together so a recorded RUL number is never read as a validated
physical failure time.
"""

from __future__ import annotations

from dataclasses import dataclass

from industrial_phm.analysis.view import AnalysisView, AnalysisViewError

_UNCERTAINTY_CAPABILITIES = ("prediction-interval", "uncertainty-calibration")
_FAILURE_THRESHOLD_CAPABILITY = "validated-physical-failure-threshold"


@dataclass(frozen=True, slots=True)
class PrognosticsMethodRow:
    """One method's recorded estimate and validation error for one asset."""

    method_id: str
    kind: str
    last_recorded_acquisition_index: int
    last_recorded_remaining_useful_life: float
    prediction_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_signed_error: float
    normalized_mean_absolute_error: float


@dataclass(frozen=True, slots=True)
class PrognosticsAssetSummary:
    """Everything a user surface must show together for one asset's RUL evidence.

    ``primary_method_id`` stays ``None`` while no method selection is validated, so a surface
    must present ``methods`` as development comparison rather than as one operational answer.
    """

    asset_id: str
    target_definition_id: str
    target_unit: str
    target_formula: str
    endpoint_semantics: str
    prediction_alignment: str
    target_is_clipped: bool
    support_definition: str
    support_first_acquisition: int
    support_prediction_count: int
    methods: tuple[PrognosticsMethodRow, ...]
    primary_method_id: str | None
    uncertainty_interval_available: bool
    physical_failure_threshold_validated: bool
    evidence_class: str
    artifact_path: str

    @property
    def target_description(self) -> str:
        """Return the plain-language meaning of one predicted unit."""
        return (
            f"{self.target_unit} until the {self.endpoint_semantics.replace('-', ' ')} "
            f"of the recorded run ({self.target_formula})"
        )

    @property
    def estimate_range(self) -> tuple[float, float]:
        """Return the lowest and highest recorded estimate across compared methods."""
        values = [row.last_recorded_remaining_useful_life for row in self.methods]
        return (min(values), max(values))

    @property
    def has_negative_estimate(self) -> bool:
        """Return whether any compared method recorded a negative remaining-life estimate."""
        return any(row.last_recorded_remaining_useful_life < 0.0 for row in self.methods)


def summarize_prognostics_for_asset(
    view: AnalysisView,
    asset_id: str,
) -> PrognosticsAssetSummary:
    """Collect the recorded prognostics facts one asset surface must show together."""
    evidence = view.require_prognostics_evidence()
    rows: list[PrognosticsMethodRow] = []
    for method in evidence.methods:
        asset = next((item for item in method.assets if item.asset_id == asset_id), None)
        if asset is None:
            raise AnalysisViewError(
                f"method {method.method_id!r} has no recorded evidence for asset {asset_id!r}"
            )
        rows.append(
            PrognosticsMethodRow(
                method_id=method.method_id,
                kind=method.kind,
                last_recorded_acquisition_index=asset.last_recorded_acquisition_index,
                last_recorded_remaining_useful_life=asset.last_recorded_remaining_useful_life,
                prediction_count=asset.prediction_count,
                mean_absolute_error=asset.mean_absolute_error,
                root_mean_squared_error=asset.root_mean_squared_error,
                mean_signed_error=asset.mean_signed_error,
                normalized_mean_absolute_error=asset.normalized_mean_absolute_error,
            )
        )

    available = set(view.available_capabilities)
    return PrognosticsAssetSummary(
        asset_id=asset_id,
        target_definition_id=evidence.target_definition_id,
        target_unit=evidence.target_unit,
        target_formula=evidence.target_formula,
        endpoint_semantics=evidence.endpoint_semantics,
        prediction_alignment=evidence.prediction_alignment,
        target_is_clipped=evidence.target_is_clipped,
        support_definition=evidence.support_definition,
        support_first_acquisition=evidence.support_first_acquisition,
        support_prediction_count=evidence.support_prediction_count,
        methods=tuple(rows),
        primary_method_id=evidence.primary_method_id,
        uncertainty_interval_available=all(
            capability in available for capability in _UNCERTAINTY_CAPABILITIES
        ),
        physical_failure_threshold_validated=_FAILURE_THRESHOLD_CAPABILITY in available,
        evidence_class=view.evidence_class,
        artifact_path=view.artifact_path,
    )


def prognostics_asset_ids(view: AnalysisView) -> tuple[str, ...]:
    """Return every asset that carries recorded prognostics evidence for all methods."""
    evidence = view.require_prognostics_evidence()
    if not evidence.methods:
        raise AnalysisViewError("prognostics evidence contains no compared methods")
    shared = set.intersection(
        *({asset.asset_id for asset in method.assets} for method in evidence.methods)
    )
    return tuple(sorted(shared))
