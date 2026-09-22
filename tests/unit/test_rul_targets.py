from dataclasses import replace

import pytest

from industrial_phm.prognostics import (
    RulEndpointKind,
    RulTargetError,
    RulTargetObservation,
    RulTargetSeries,
)


def _observation(
    *,
    asset_id: str = "asset-a",
    partition_id: str = "train",
    source_observation_id: str = "asset-a:observation-1",
    remaining_useful_life: float = 3.0,
) -> RulTargetObservation:
    return RulTargetObservation(
        asset_id=asset_id,
        partition_id=partition_id,
        source_observation_id=source_observation_id,
        remaining_useful_life=remaining_useful_life,
    )


def test_rul_target_observation_accepts_zero_and_normalizes_numeric_value() -> None:
    observation = _observation(remaining_useful_life=0)

    assert observation.remaining_useful_life == 0.0


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_rul_target_observation_rejects_invalid_remaining_life(value: float) -> None:
    with pytest.raises(RulTargetError, match="finite and non-negative"):
        _observation(remaining_useful_life=value)


def test_rul_target_series_freezes_ordered_observations() -> None:
    first = _observation()
    second = _observation(
        source_observation_id="asset-a:observation-2",
        remaining_useful_life=2.0,
    )

    series = RulTargetSeries(
        target_definition_id="recorded-end-v1",
        unit="cycle",
        asset_id="asset-a",
        partition_id="train",
        observations=[first, second],
    )

    assert series.observations == (first, second)
    assert isinstance(series.observations, tuple)
    assert series.endpoint_kind is RulEndpointKind.UNKNOWN


@pytest.mark.parametrize(
    ("observation", "message"),
    [
        (_observation(asset_id="asset-b"), "asset_id"),
        (_observation(partition_id="validation"), "partition_id"),
    ],
)
def test_rul_target_series_rejects_identity_drift(
    observation: RulTargetObservation,
    message: str,
) -> None:
    with pytest.raises(RulTargetError, match=message):
        RulTargetSeries(
            target_definition_id="recorded-end-v1",
            unit="cycle",
            asset_id="asset-a",
            partition_id="train",
            observations=(observation,),
        )


def test_rul_target_series_rejects_duplicate_source_identity() -> None:
    first = _observation()
    duplicate = replace(first, remaining_useful_life=2.0)

    with pytest.raises(RulTargetError, match="identities must be unique"):
        RulTargetSeries(
            target_definition_id="recorded-end-v1",
            unit="cycle",
            asset_id="asset-a",
            partition_id="train",
            observations=(first, duplicate),
        )

def test_rul_target_series_accepts_confirmed_failure_endpoint() -> None:
    series = RulTargetSeries(
        target_definition_id="failure-rul-v1",
        unit="cycle",
        asset_id="asset-a",
        partition_id="train",
        observations=(_observation(),),
        endpoint_kind=RulEndpointKind.CONFIRMED_FAILURE,
    )

    assert series.endpoint_kind is RulEndpointKind.CONFIRMED_FAILURE


def test_rul_target_series_rejects_right_censored_exact_targets() -> None:
    with pytest.raises(RulTargetError, match="right-censored lifecycle"):
        RulTargetSeries(
            target_definition_id="censored-rul-v1",
            unit="cycle",
            asset_id="asset-a",
            partition_id="train",
            observations=(_observation(),),
            endpoint_kind=RulEndpointKind.RIGHT_CENSORED,
        )


def test_rul_target_series_rejects_untyped_endpoint_kind() -> None:
    with pytest.raises(RulTargetError, match="endpoint_kind"):
        RulTargetSeries(
            target_definition_id="recorded-end-v1",
            unit="cycle",
            asset_id="asset-a",
            partition_id="train",
            observations=(_observation(),),
            endpoint_kind="observed-record-end",  # type: ignore[arg-type]
        )
