"""Dataset-neutral Isolation Forest fitting and anomaly scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

from industrial_phm.experiments.config import ExperimentConfig, ModelFamily
from industrial_phm.models.input import ModelFitInput, ModelScoringInput
from industrial_phm.models.output import AnomalyScores

_MODEL_PARAMETER_NAMES = {
    "n_estimators",
    "max_samples",
    "contamination",
    "max_features",
    "bootstrap",
}


class IsolationForestError(ValueError):
    """Raised when Isolation Forest configuration or model input is incompatible."""


class _IsolationForestEstimator(Protocol):
    def fit(self, feature_rows: Sequence[Sequence[float]]) -> _IsolationForestEstimator: ...

    def score_samples(self, feature_rows: Sequence[Sequence[float]]) -> Sequence[float]: ...


@dataclass(frozen=True, slots=True)
class _IsolationForestParameters:
    n_estimators: int
    max_samples: Literal["auto"] | int | float
    contamination: Literal["auto"] | float
    max_features: int | float
    bootstrap: bool


@dataclass(frozen=True, slots=True)
class FittedIsolationForest:
    """Fitted Isolation Forest bound to one experiment and feature schema."""

    experiment_id: str
    feature_set_id: str
    feature_names: tuple[str, ...]
    sampling_policy_id: str
    random_seed: int
    source_observation_count: int
    fit_observation_count: int
    _estimator: _IsolationForestEstimator = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in ("experiment_id", "feature_set_id", "sampling_policy_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise IsolationForestError(f"{field_name} must be a trimmed non-empty string")
        feature_names = tuple(self.feature_names)
        if not feature_names or len(feature_names) != len(set(feature_names)):
            raise IsolationForestError("feature_names must contain unique values")
        if any(not name.strip() or name != name.strip() for name in feature_names):
            raise IsolationForestError("feature_names must contain trimmed non-empty strings")
        object.__setattr__(self, "feature_names", feature_names)
        if (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
            or self.random_seed < 0
        ):
            raise IsolationForestError("random_seed must be a non-negative integer")
        for field_name in ("source_observation_count", "fit_observation_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise IsolationForestError(f"{field_name} must be a positive integer")

    def score(self, model_input: ModelScoringInput) -> AnomalyScores:
        """Score prepared observations while preserving input identity and ordering."""
        if model_input.experiment_id != self.experiment_id:
            raise IsolationForestError(
                "model-scoring experiment_id does not match the fitted Isolation Forest"
            )
        if model_input.feature_set_id != self.feature_set_id:
            raise IsolationForestError(
                "model-scoring feature_set_id does not match the fitted Isolation Forest"
            )
        if tuple(model_input.feature_names) != self.feature_names:
            raise IsolationForestError(
                "model-scoring feature schema does not match the fitted Isolation Forest"
            )

        raw_scores = self._estimator.score_samples(model_input.feature_rows)
        return AnomalyScores(
            experiment_id=self.experiment_id,
            source_observation_ids=model_input.source_observation_ids,
            scores=tuple(-float(score) for score in raw_scores),
        )


def fit_isolation_forest(
    config: ExperimentConfig,
    model_input: ModelFitInput,
) -> FittedIsolationForest:
    """Validate, fit, and bind an Isolation Forest to prepared model-fit input."""
    _validate_fit_context(config, model_input)
    parameters = _parse_parameters(config.model_parameters)
    if isinstance(parameters.max_features, int) and parameters.max_features > len(
        model_input.feature_names
    ):
        raise IsolationForestError(
            "Isolation Forest max_features cannot exceed the model-fit feature count"
        )

    estimator = cast(
        _IsolationForestEstimator,
        IsolationForest(
            n_estimators=parameters.n_estimators,
            max_samples=parameters.max_samples,
            contamination=parameters.contamination,
            max_features=parameters.max_features,
            bootstrap=parameters.bootstrap,
            n_jobs=1,
            random_state=model_input.random_seed,
        ),
    )
    estimator.fit(model_input.feature_rows)
    return FittedIsolationForest(
        experiment_id=model_input.experiment_id,
        feature_set_id=model_input.feature_set_id,
        feature_names=tuple(model_input.feature_names),
        sampling_policy_id=model_input.sampling_policy_id,
        random_seed=model_input.random_seed,
        source_observation_count=model_input.source_observation_count,
        fit_observation_count=model_input.fit_observation_count,
        _estimator=estimator,
    )


def _validate_fit_context(config: ExperimentConfig, model_input: ModelFitInput) -> None:
    if config.model_family is not ModelFamily.ISOLATION_FOREST:
        raise IsolationForestError("model_family must be isolation-forest")
    expected = (
        ("experiment_id", model_input.experiment_id, config.experiment_id),
        ("feature_set_id", model_input.feature_set_id, config.feature_set_id),
        ("feature_names", tuple(model_input.feature_names), tuple(config.selected_features)),
        ("sampling_policy_id", model_input.sampling_policy_id, config.sampling_policy_id),
        ("random_seed", model_input.random_seed, config.random_seed),
    )
    for field_name, observed, configured in expected:
        if observed != configured:
            raise IsolationForestError(
                f"model-fit input {field_name} does not match experiment config"
            )


def _parse_parameters(
    values: Mapping[str, str | int | float | bool],
) -> _IsolationForestParameters:
    observed_names = set(values)
    if observed_names != _MODEL_PARAMETER_NAMES:
        missing = sorted(_MODEL_PARAMETER_NAMES - observed_names)
        unknown = sorted(observed_names - _MODEL_PARAMETER_NAMES)
        raise IsolationForestError(
            "Isolation Forest parameters do not match the supported contract; "
            f"missing={missing}, unknown={unknown}"
        )

    return _IsolationForestParameters(
        n_estimators=_positive_int(values["n_estimators"], "n_estimators"),
        max_samples=_max_samples(values["max_samples"]),
        contamination=_contamination(values["contamination"]),
        max_features=_max_features(values["max_features"]),
        bootstrap=_boolean(values["bootstrap"], "bootstrap"),
    )


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise IsolationForestError(f"Isolation Forest {field_name} must be a positive integer")
    return value


def _max_samples(value: object) -> Literal["auto"] | int | float:
    if value == "auto":
        return "auto"
    if isinstance(value, bool):
        raise IsolationForestError(
            "Isolation Forest max_samples must be 'auto', a positive integer, or a float in (0, 1]"
        )
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and math.isfinite(value) and 0.0 < value <= 1.0:
        return value
    raise IsolationForestError(
        "Isolation Forest max_samples must be 'auto', a positive integer, or a float in (0, 1]"
    )


def _contamination(value: object) -> Literal["auto"] | float:
    if value == "auto":
        return "auto"
    if isinstance(value, float) and math.isfinite(value) and 0.0 < value <= 0.5:
        return value
    raise IsolationForestError(
        "Isolation Forest contamination must be 'auto' or a float in (0, 0.5]"
    )


def _max_features(value: object) -> int | float:
    if isinstance(value, bool):
        raise IsolationForestError(
            "Isolation Forest max_features must be a positive integer or a float in (0, 1]"
        )
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and math.isfinite(value) and 0.0 < value <= 1.0:
        return value
    raise IsolationForestError(
        "Isolation Forest max_features must be a positive integer or a float in (0, 1]"
    )


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise IsolationForestError(f"Isolation Forest {field_name} must be a boolean")
    return value
