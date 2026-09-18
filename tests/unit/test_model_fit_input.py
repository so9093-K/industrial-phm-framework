from dataclasses import FrozenInstanceError

import pytest

from industrial_phm.models import ModelFitInput, ModelFitInputError


def test_model_fit_input_preserves_dataset_neutral_rows_and_source_identity() -> None:
    prepared = ModelFitInput(
        experiment_id="candidate-v1",
        feature_set_id="features-v1",
        feature_names=("feature.a", "feature.b"),
        rows=((1.0, 2.0), (3.0, 4.0)),
        source_observation_ids=("observation-1", "observation-2"),
        sampling_policy_id="reference-policy-v1",
        random_seed=42,
        input_observation_count=3,
    )

    assert prepared.rows == ((1.0, 2.0), (3.0, 4.0))
    assert prepared.source_observation_ids == ("observation-1", "observation-2")
    assert prepared.output_observation_count == 2

    with pytest.raises(FrozenInstanceError):
        prepared.random_seed = 43  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"rows": ()}, "at least one row"),
        ({"rows": ((1.0,),)}, "width must be 2"),
        ({"rows": ((1.0, float("inf")),)}, "non-finite"),
        ({"source_observation_ids": ("observation-1",)}, "same number"),
        ({"random_seed": -1}, "non-negative"),
        ({"input_observation_count": 0}, "positive integer"),
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
        "rows": ((1.0, 2.0), (3.0, 4.0)),
        "source_observation_ids": ("observation-1", "observation-2"),
        "sampling_policy_id": "reference-policy-v1",
        "random_seed": 42,
        "input_observation_count": 2,
    }
    values.update(changes)

    with pytest.raises(ModelFitInputError, match=message):
        ModelFitInput(**values)  # type: ignore[arg-type]
