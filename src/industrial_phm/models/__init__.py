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

__all__ = [
    "MEAN_SQUARED_RECONSTRUCTION_ERROR_ID",
    "AnomalyScores",
    "AnomalyScoresError",
    "FittedIsolationForest",
    "FittedLstmAutoencoder",
    "IsolationForestError",
    "LstmAutoencoderError",
    "LstmAutoencoderTrainingProvenance",
    "ModelFitInput",
    "ModelFitInputError",
    "ModelScoringInput",
    "ModelScoringInputError",
    "ReconstructionScores",
    "ReconstructionScoringError",
    "SequenceReconstructions",
    "fit_isolation_forest",
    "fit_lstm_autoencoder",
    "score_reconstructions",
]
