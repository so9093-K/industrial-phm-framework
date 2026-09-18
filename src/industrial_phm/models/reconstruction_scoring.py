"""Dataset-neutral scoring contracts for sequence reconstructions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from industrial_phm.models.lstm_autoencoder import SequenceReconstructions
from industrial_phm.sequences import SequenceConstruction, SequenceWindowSpec

MEAN_SQUARED_RECONSTRUCTION_ERROR_ID = "mean-squared-reconstruction-error-v1"


class ReconstructionScoringError(ValueError):
    """Raised when reconstruction scoring inputs or results violate their contract."""


@dataclass(frozen=True, slots=True)
class ReconstructionScores:
    """Window scores and feature residuals aligned to source observations."""

    experiment_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    spec: SequenceWindowSpec
    window_ids: Sequence[str]
    sequence_ids: Sequence[str]
    asset_ids: Sequence[str]
    partition_ids: Sequence[str]
    aligned_source_observation_ids: Sequence[str]
    aligned_source_positions: Sequence[int]
    scores: Sequence[float]
    feature_residuals: Sequence[Sequence[float]]
    score_semantics_id: str = field(
        default=MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
        init=False,
    )
    higher_is_more_anomalous: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        _validate_text(self.experiment_id, "experiment_id")
        _validate_text(self.feature_set_id, "feature_set_id")
        feature_names = _validated_names(self.feature_names)
        if not isinstance(self.spec, SequenceWindowSpec):
            raise ReconstructionScoringError("spec must be a SequenceWindowSpec")

        identity_fields = (
            "window_ids",
            "sequence_ids",
            "asset_ids",
            "partition_ids",
            "aligned_source_observation_ids",
        )
        identities: dict[str, tuple[str, ...]] = {}
        for field_name in identity_fields:
            values = tuple(getattr(self, field_name))
            if not values:
                raise ReconstructionScoringError(f"{field_name} must contain at least one value")
            for value in values:
                _validate_text(value, field_name)
            identities[field_name] = values

        positions = tuple(self.aligned_source_positions)
        for position in positions:
            if isinstance(position, bool) or not isinstance(position, int) or position < 0:
                raise ReconstructionScoringError(
                    "aligned_source_positions must contain non-negative integers"
                )

        scores = _finite_non_negative_values(self.scores, "scores")
        feature_residuals = tuple(
            _finite_non_negative_values(row, f"feature_residuals row {row_index}")
            for row_index, row in enumerate(self.feature_residuals)
        )
        window_count = len(scores)
        if not window_count:
            raise ReconstructionScoringError("scores must contain at least one value")
        if any(len(values) != window_count for values in identities.values()):
            raise ReconstructionScoringError(
                "score identities and scores must contain the same window count"
            )
        if len(positions) != window_count or len(feature_residuals) != window_count:
            raise ReconstructionScoringError(
                "aligned positions, feature residuals, and scores must contain "
                "the same window count"
            )
        if len(set(identities["window_ids"])) != window_count:
            raise ReconstructionScoringError("window_ids must contain unique values")
        if len(set(identities["aligned_source_observation_ids"])) != window_count:
            raise ReconstructionScoringError(
                "aligned_source_observation_ids must contain unique values"
            )
        for row_index, (score, residuals) in enumerate(zip(scores, feature_residuals, strict=True)):
            if len(residuals) != len(feature_names):
                raise ReconstructionScoringError(
                    f"feature_residuals row {row_index} width must be {len(feature_names)}"
                )
            expected_score = math.fsum(residuals) / len(feature_names)
            if not math.isclose(score, expected_score, rel_tol=1e-12, abs_tol=1e-15):
                raise ReconstructionScoringError(
                    f"score {row_index} must equal the mean feature residual"
                )

        object.__setattr__(self, "feature_names", feature_names)
        for field_name, values in identities.items():
            object.__setattr__(self, field_name, values)
        object.__setattr__(self, "aligned_source_positions", positions)
        object.__setattr__(self, "scores", scores)
        object.__setattr__(self, "feature_residuals", feature_residuals)

    @property
    def window_count(self) -> int:
        """Return the number of scored windows and aligned source observations."""
        return len(self.scores)


def score_reconstructions(
    construction: SequenceConstruction,
    reconstructions: SequenceReconstructions,
) -> ReconstructionScores:
    """Calculate right-edge-aligned MSE evidence from immutable sequence windows."""
    _validate_scoring_context(construction, reconstructions)
    feature_count = len(construction.feature_names)
    sequence_length = construction.spec.length
    feature_residuals: list[tuple[float, ...]] = []
    scores: list[float] = []

    for model_input, reconstructed in zip(
        reconstructions.model_input_values,
        reconstructions.values,
        strict=True,
    ):
        residuals = tuple(
            math.fsum(
                (model_input[time_index][feature_index] - reconstructed[time_index][feature_index])
                ** 2
                for time_index in range(sequence_length)
            )
            / sequence_length
            for feature_index in range(feature_count)
        )
        feature_residuals.append(residuals)
        scores.append(math.fsum(residuals) / feature_count)

    return ReconstructionScores(
        experiment_id=reconstructions.experiment_id,
        feature_set_id=construction.feature_set_id,
        feature_names=construction.feature_names,
        spec=construction.spec,
        window_ids=reconstructions.window_ids,
        sequence_ids=reconstructions.sequence_ids,
        asset_ids=reconstructions.asset_ids,
        partition_ids=reconstructions.partition_ids,
        aligned_source_observation_ids=reconstructions.aligned_source_observation_ids,
        aligned_source_positions=tuple(
            window.source_positions[-1] for window in construction.windows
        ),
        scores=scores,
        feature_residuals=feature_residuals,
    )


def _validate_scoring_context(
    construction: SequenceConstruction,
    reconstructions: SequenceReconstructions,
) -> None:
    if not isinstance(construction, SequenceConstruction):
        raise ReconstructionScoringError("construction must be a SequenceConstruction")
    if not isinstance(reconstructions, SequenceReconstructions):
        raise ReconstructionScoringError("reconstructions must be a SequenceReconstructions")
    if reconstructions.feature_set_id != construction.feature_set_id:
        raise ReconstructionScoringError(
            "reconstruction feature_set_id must match sequence construction"
        )
    if tuple(reconstructions.feature_names) != tuple(construction.feature_names):
        raise ReconstructionScoringError(
            "reconstruction feature schema must match sequence construction"
        )
    if reconstructions.spec != construction.spec:
        raise ReconstructionScoringError(
            "reconstruction window spec must match sequence construction"
        )

    expected_identities = {
        "window_ids": tuple(window.window_id for window in construction.windows),
        "sequence_ids": tuple(window.sequence_id for window in construction.windows),
        "asset_ids": tuple(window.asset_id for window in construction.windows),
        "partition_ids": tuple(window.partition_id for window in construction.windows),
        "aligned_source_observation_ids": tuple(
            window.aligned_source_observation_id for window in construction.windows
        ),
    }
    for field_name, expected in expected_identities.items():
        if tuple(getattr(reconstructions, field_name)) != expected:
            raise ReconstructionScoringError(
                f"reconstruction {field_name} must match sequence construction order"
            )


def _validated_names(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise ReconstructionScoringError("feature_names must contain at least one value")
    for value in result:
        _validate_text(value, "feature_names")
    if len(result) != len(set(result)):
        raise ReconstructionScoringError("feature_names must contain unique values")
    return result


def _finite_non_negative_values(
    values: Sequence[float],
    field_name: str,
) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ReconstructionScoringError(f"{field_name} must contain numerical values")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ReconstructionScoringError(f"{field_name} must contain finite values")
        if numeric < 0.0:
            raise ReconstructionScoringError(f"{field_name} must contain non-negative values")
        result.append(numeric)
    return tuple(result)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ReconstructionScoringError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ReconstructionScoringError(f"{field_name} must not contain surrounding whitespace")
