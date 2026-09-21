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
from industrial_phm.models.lstm_autoencoder import (
    FittedLstmAutoencoder,
    LstmAutoencoderError,
    LstmAutoencoderTrainingProvenance,
    SequenceReconstructions,
    fit_lstm_autoencoder,
)
from industrial_phm.models.output import AnomalyScores, AnomalyScoresError
from industrial_phm.models.reconstruction_scoring import (
    MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
    ReconstructionScores,
    ReconstructionScoringError,
    score_reconstructions,
)
from industrial_phm.models.rul_ridge_regression import (
    FittedRulRidgeRegressor,
    RulRidgeRegressionError,
    fit_rul_ridge_regression,
)

__all__ = [
    "MEAN_SQUARED_RECONSTRUCTION_ERROR_ID",
    "AnomalyScores",
    "AnomalyScoresError",
    "FittedIsolationForest",
    "FittedLstmAutoencoder",
    "FittedRulRidgeRegressor",
    "IsolationForestError",
    "LstmAutoencoderError",
    "LstmAutoencoderTrainingProvenance",
    "ModelFitInput",
    "ModelFitInputError",
    "ModelScoringInput",
    "ModelScoringInputError",
    "ReconstructionScores",
    "ReconstructionScoringError",
    "RulRidgeRegressionError",
    "SequenceReconstructions",
    "fit_isolation_forest",
    "fit_lstm_autoencoder",
    "fit_rul_ridge_regression",
    "score_reconstructions",
]
