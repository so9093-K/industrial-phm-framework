"""Dataset-neutral Ridge regression for supervised RUL point prediction."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from sklearn.linear_model import Ridge  # type: ignore[import-untyped]

from industrial_phm.experiments.config import ExperimentConfig, ModelFamily
from industrial_phm.models.input import ModelFitInput, ModelScoringInput

_MODEL_PARAMETER_NAMES = {"alpha", "fit_intercept", "solver"}


class RulRidgeRegressionError(ValueError):
    """Raised when Ridge RUL configuration, targets, or model input is incompatible."""


class _RidgeEstimator(Protocol):
    def fit(
        self,
        feature_rows: Sequence[Sequence[float]],
        target_values: Sequence[float],
    ) -> _RidgeEstimator: ...

    def predict(self, feature_rows: Sequence[Sequence[float]]) -> Sequence[float]: ...


@dataclass(frozen=True, slots=True)
class _RidgeParameters:
    alpha: float
    fit_intercept: bool
    solver: Literal["svd"]


@dataclass(frozen=True, slots=True)
class FittedRulRidgeRegressor:
    """Fitted Ridge regressor bound to one experiment and feature schema."""

    experiment_id: str
    feature_set_id: str
    feature_names: tuple[str, ...]
    sampling_policy_id: str
    source_observation_count: int
    reference_observation_count: int
    fit_observation_count: int
    alpha: float
    fit_intercept: bool
    solver: Literal["svd"]
    _estimator: _RidgeEstimator = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in ("experiment_id", "feature_set_id", "sampling_policy_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise RulRidgeRegressionError(f"{field_name} must be a trimmed non-empty string")

        feature_names = tuple(self.feature_names)
        if not feature_names or len(feature_names) != len(set(feature_names)):
            raise RulRidgeRegressionError("feature_names must contain unique values")
        if any(not name.strip() or name != name.strip() for name in feature_names):
            raise RulRidgeRegressionError("feature_names must contain trimmed non-empty strings")
        object.__setattr__(self, "feature_names", feature_names)

        for field_name in (
            "source_observation_count",
            "reference_observation_count",
            "fit_observation_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise RulRidgeRegressionError(f"{field_name} must be a positive integer")

        if not math.isfinite(self.alpha) or self.alpha < 0.0:
            raise RulRidgeRegressionError("alpha must be finite and non-negative")
        if not isinstance(self.fit_intercept, bool):
            raise RulRidgeRegressionError("fit_intercept must be a boolean")
        if self.solver != "svd":
            raise RulRidgeRegressionError("solver must be 'svd'")

    def predict(self, model_input: ModelScoringInput) -> tuple[float, ...]:
        """Predict prepared observations without clipping model output."""
        if model_input.experiment_id != self.experiment_id:
            raise RulRidgeRegressionError(
                "model-scoring experiment_id does not match the fitted Ridge regressor"
            )
        if model_input.feature_set_id != self.feature_set_id:
            raise RulRidgeRegressionError(
                "model-scoring feature_set_id does not match the fitted Ridge regressor"
            )
        if tuple(model_input.feature_names) != self.feature_names:
            raise RulRidgeRegressionError(
                "model-scoring feature schema does not match the fitted Ridge regressor"
            )

        predictions = tuple(
            float(value) for value in self._estimator.predict(model_input.feature_rows)
        )
        if len(predictions) != model_input.observation_count:
            raise RulRidgeRegressionError(
                "Ridge prediction count does not match model-scoring input"
            )
        if not all(math.isfinite(value) for value in predictions):
            raise RulRidgeRegressionError("Ridge predictions must be finite")
        return predictions


def fit_rul_ridge_regression(
    config: ExperimentConfig,
    model_input: ModelFitInput,
    target_values: Sequence[float],
) -> FittedRulRidgeRegressor:
    """Fit Ridge from prepared feature rows and row-aligned raw RUL targets."""
    _validate_fit_context(config, model_input)
    targets = _validated_targets(target_values, expected_count=model_input.fit_observation_count)
    parameters = _parse_parameters(config.model_parameters)

    estimator = cast(
        _RidgeEstimator,
        Ridge(
            alpha=parameters.alpha,
            fit_intercept=parameters.fit_intercept,
            solver=parameters.solver,
        ),
    )
    estimator.fit(model_input.feature_rows, targets)
    return FittedRulRidgeRegressor(
        experiment_id=model_input.experiment_id,
        feature_set_id=model_input.feature_set_id,
        feature_names=tuple(model_input.feature_names),
        sampling_policy_id=model_input.sampling_policy_id,
        source_observation_count=model_input.source_observation_count,
        reference_observation_count=model_input.reference_observation_count,
        fit_observation_count=model_input.fit_observation_count,
        alpha=parameters.alpha,
        fit_intercept=parameters.fit_intercept,
        solver=parameters.solver,
        _estimator=estimator,
    )


def _validate_fit_context(config: ExperimentConfig, model_input: ModelFitInput) -> None:
    if config.model_family is not ModelFamily.RIDGE_REGRESSION:
        raise RulRidgeRegressionError("model_family must be ridge-regression")

    expected = (
        ("experiment_id", model_input.experiment_id, config.experiment_id),
        ("feature_set_id", model_input.feature_set_id, config.feature_set_id),
        ("feature_names", tuple(model_input.feature_names), tuple(config.selected_features)),
        ("sampling_policy_id", model_input.sampling_policy_id, config.sampling_policy_id),
    )
    for field_name, observed, configured in expected:
        if observed != configured:
            raise RulRidgeRegressionError(
                f"model-fit input {field_name} does not match experiment config"
            )


def _validated_targets(
    values: Sequence[float],
    *,
    expected_count: int,
) -> tuple[float, ...]:
    targets: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RulRidgeRegressionError("target_values must contain only numerical values")
        target = float(value)
        if not math.isfinite(target) or target < 0.0:
            raise RulRidgeRegressionError("target_values must contain finite non-negative values")
        targets.append(target)

    result = tuple(targets)
    if len(result) != expected_count:
        raise RulRidgeRegressionError(
            f"target_values count must be {expected_count}, got {len(result)}"
        )
    return result


def _parse_parameters(
    values: Mapping[str, str | int | float | bool],
) -> _RidgeParameters:
    observed_names = set(values)
    if observed_names != _MODEL_PARAMETER_NAMES:
        missing = sorted(_MODEL_PARAMETER_NAMES - observed_names)
        unknown = sorted(observed_names - _MODEL_PARAMETER_NAMES)
        raise RulRidgeRegressionError(
            "Ridge regression parameters do not match the supported contract; "
            f"missing={missing}, unknown={unknown}"
        )

    alpha = values["alpha"]
    if isinstance(alpha, bool) or not isinstance(alpha, int | float):
        raise RulRidgeRegressionError("Ridge alpha must be numerical")
    alpha_value = float(alpha)
    if not math.isfinite(alpha_value) or alpha_value < 0.0:
        raise RulRidgeRegressionError("Ridge alpha must be finite and non-negative")

    fit_intercept = values["fit_intercept"]
    if not isinstance(fit_intercept, bool):
        raise RulRidgeRegressionError("Ridge fit_intercept must be a boolean")

    solver = values["solver"]
    if solver != "svd":
        raise RulRidgeRegressionError("Ridge solver must be 'svd'")

    return _RidgeParameters(
        alpha=alpha_value,
        fit_intercept=fit_intercept,
        solver="svd",
    )
