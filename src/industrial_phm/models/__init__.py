"""Dataset-neutral model fitting and scoring contracts."""

from industrial_phm.models.input import (
    ModelFitInput,
    ModelFitInputError,
    ModelScoringInput,
    ModelScoringInputError,
)

__all__ = [
    "ModelFitInput",
    "ModelFitInputError",
    "ModelScoringInput",
    "ModelScoringInputError",
]
