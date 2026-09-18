from dataclasses import FrozenInstanceError

import pytest

from industrial_phm.models import (
    ModelFitInput,
    ModelFitInputError,
    ModelScoringInput,
    ModelScoringInputError,
)


def test_model_fit_input_uses_explicit_feature_and_sampling_names() -> None:
    prepared = ModelFitInput(
        experiment_id="candidate-v1",
        feature_set_id="features-v1",
        feature_names=("feature.a", "feature.b"),
        feature_rows=((1.0, 2.0), (3.0, 4.0)),
        source_observation_ids=("observation-1", "observation-2"),
        sampling_policy_id="reference-policy-v1",
        random_seed=42,
        source_observation_count=3,
    )

    assert prepared.feature_rows == ((1.0, 2.0), (3.0, 4.0))
    assert prepared.source_observation_ids == ("observation-1", "observation-2")
    assert prepared.source_observation_count == 3
    assert prepared.fit_observation_count == 2

    with pytest.raises(FrozenInstanceError):
        prepared.random_seed = 43  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"feature_rows": ()}, "at least one feature row"),
        ({"feature_rows": ((1.0,),)}, "width must be 2"),
        ({"feature_rows": ((1.0, float("inf")),)}, "non-finite"),
        ({"source_observation_ids": ("observation-1",)}, "same number"),
        ({"random_seed": -1}, "non-negative"),
        ({"source_observation_count": 0}, "positive integer"),
    ],
)
def test_model_fit_input_rejects_invalid_contract_values(
    changes: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "experiment_id": "candidate-v1",
        "feature_set_id": "features-v1",
        "feature_names": ("feature.a", "feature.b"),
        "feature_rows": ((1.0, 2.0), (3.0, 4.0)),
        "source_observation_ids": ("observation-1", "observation-2"),
        "sampling_policy_id": "reference-policy-v1",
        "random_seed": 42,
        "source_observation_count": 2,
    }
    values.update(changes)

    with pytest.raises(ModelFitInputError, match=message):
        ModelFitInput(**values)  # type: ignore[arg-type]


def test_model_scoring_input_requires_unique_observation_identity() -> None:
    prepared = ModelScoringInput(
        experiment_id="candidate-v1",
        feature_set_id="features-v1",
        feature_names=("feature.a", "feature.b"),
        feature_rows=((1.0, 2.0), (3.0, 4.0)),
        source_observation_ids=("observation-1", "observation-2"),
    )

    assert prepared.feature_rows == ((1.0, 2.0), (3.0, 4.0))
    assert prepared.observation_count == 2

    with pytest.raises(ModelScoringInputError, match="unique"):
        ModelScoringInput(
            experiment_id="candidate-v1",
            feature_set_id="features-v1",
            feature_names=("feature.a", "feature.b"),
            feature_rows=((1.0, 2.0), (3.0, 4.0)),
            source_observation_ids=("observation-1", "observation-1"),
        )
