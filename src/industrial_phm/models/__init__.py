"""Dataset-neutral model fitting and scoring contracts."""

from industrial_phm.models.input import (
    ModelFitInput,
    ModelFitInputError,
    ModelScoringInput,
    ModelScoringInputError,
)
from industrial_phm.models.isolation_forest import (
    FittedIsolationForest,
    IsolationForestError,
    fit_isolation_forest,
)
from industrial_phm.models.output import AnomalyScores, AnomalyScoresError

__all__ = [
    "AnomalyScores",
    "AnomalyScoresError",
    "FittedIsolationForest",
    "IsolationForestError",
    "ModelFitInput",
    "ModelFitInputError",
    "ModelScoringInput",
    "ModelScoringInputError",
    "fit_isolation_forest",
]
