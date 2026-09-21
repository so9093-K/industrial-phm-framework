from dataclasses import replace

import pytest

from industrial_phm.prognostics import (
    RulPredictionError,
    RulPredictionObservation,
    RulPredictionSeries,
)


def _observation(
    *,
    asset_id: str = "asset-a",
    partition_id: str = "validation",
    source_observation_id: str = "asset-a:observation-1",
    predicted_remaining_useful_life: float = 3.0,
) -> RulPredictionObservation:
    return RulPredictionObservation(
        asset_id=asset_id,
        partition_id=partition_id,
        source_observation_id=source_observation_id,
        predicted_remaining_useful_life=predicted_remaining_useful_life,
    )


def test_rul_prediction_allows_finite_negative_value_without_clamping() -> None:
    prediction = _observation(predicted_remaining_useful_life=-2.0)

    assert prediction.predicted_remaining_useful_life == -2.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rul_prediction_rejects_non_finite_value(value: float) -> None:
    with pytest.raises(RulPredictionError, match="must be finite"):
        _observation(predicted_remaining_useful_life=value)


def test_rul_prediction_series_freezes_order_and_identity() -> None:
    first = _observation()
    second = _observation(
        source_observation_id="asset-a:observation-2",
        predicted_remaining_useful_life=2.0,
    )

    series = RulPredictionSeries(
        prediction_method_id="baseline-v1",
        target_definition_id="recorded-end-v1",
        unit="cycle",
        asset_id="asset-a",
        partition_id="validation",
        observations=[first, second],
    )

    assert series.observations == (first, second)
    assert isinstance(series.observations, tuple)


@pytest.mark.parametrize(
    ("observation", "message"),
    [
        (_observation(asset_id="asset-b"), "asset_id"),
        (_observation(partition_id="test"), "partition_id"),
    ],
)
def test_rul_prediction_series_rejects_identity_drift(
    observation: RulPredictionObservation,
    message: str,
) -> None:
    with pytest.raises(RulPredictionError, match=message):
        RulPredictionSeries(
            prediction_method_id="baseline-v1",
            target_definition_id="recorded-end-v1",
            unit="cycle",
            asset_id="asset-a",
            partition_id="validation",
            observations=(observation,),
        )


def test_rul_prediction_series_rejects_duplicate_source_identity() -> None:
    first = _observation()
    duplicate = replace(first, predicted_remaining_useful_life=2.0)

    with pytest.raises(RulPredictionError, match="identities must be unique"):
        RulPredictionSeries(
            prediction_method_id="baseline-v1",
            target_definition_id="recorded-end-v1",
            unit="cycle",
            asset_id="asset-a",
            partition_id="validation",
            observations=(first, duplicate),
        )
