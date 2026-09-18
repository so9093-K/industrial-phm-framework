from dataclasses import FrozenInstanceError, replace

import pytest

from industrial_phm.experiments import ModelFamily
from industrial_phm.models import (
    MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
    ReconstructionScoringError,
    SequenceReconstructions,
    score_reconstructions,
)
from industrial_phm.sequences import (
    SequenceFeatureObservation,
    SequenceWindowSpec,
    construct_sequence_windows,
)

_FEATURE_NAMES = ("feature.channel.rms", "feature.channel.crest_factor")
_EXPERIMENT_ID = f"{ModelFamily.LSTM_AUTOENCODER.value}-reference-v1"


def _construction():
    observations = (
        SequenceFeatureObservation(
            sequence_id="run-a",
            asset_id="asset-a",
            partition_id="validation",
            source_observation_id="run-a:observation-0",
            sequence_position=0,
            feature_values=(1.0, 2.0),
        ),
        SequenceFeatureObservation(
            sequence_id="run-a",
            asset_id="asset-a",
            partition_id="validation",
            source_observation_id="run-a:observation-1",
            sequence_position=1,
            feature_values=(3.0, 4.0),
        ),
    )
    return construct_sequence_windows(
        observations,
        feature_set_id="reference-features-v1",
        feature_names=_FEATURE_NAMES,
        spec=SequenceWindowSpec(length=2, stride=1),
    )


def _reconstructions() -> SequenceReconstructions:
    construction = _construction()
    window = construction.windows[0]
    return SequenceReconstructions(
        experiment_id=_EXPERIMENT_ID,
        feature_set_id=construction.feature_set_id,
        feature_names=construction.feature_names,
        spec=construction.spec,
        window_ids=(window.window_id,),
        sequence_ids=(window.sequence_id,),
        asset_ids=(window.asset_id,),
        partition_ids=(window.partition_id,),
        aligned_source_observation_ids=(window.aligned_source_observation_id,),
        model_input_values=(((1.0, 2.0), (3.0, 4.0)),),
        values=(((0.0, 2.0), (1.0, 5.0)),),
    )


def test_reconstruction_scoring_preserves_alignment_and_mse_semantics() -> None:
    construction = _construction()

    result = score_reconstructions(construction, _reconstructions())

    assert result.experiment_id == _EXPERIMENT_ID
    assert result.feature_set_id == construction.feature_set_id
    assert result.feature_names == _FEATURE_NAMES
    assert result.spec == construction.spec
    assert result.window_ids == (construction.windows[0].window_id,)
    assert result.sequence_ids == ("run-a",)
    assert result.asset_ids == ("asset-a",)
    assert result.partition_ids == ("validation",)
    assert result.aligned_source_observation_ids == ("run-a:observation-1",)
    assert result.aligned_source_positions == (1,)
    assert result.feature_residuals == ((2.5, 0.5),)
    assert result.scores == (1.5,)
    assert result.window_count == 1
    assert result.score_semantics_id == MEAN_SQUARED_RECONSTRUCTION_ERROR_ID
    assert result.higher_is_more_anomalous is True

    with pytest.raises(FrozenInstanceError):
        result.scores = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"feature_set_id": "other-features-v1"}, "feature_set_id"),
        ({"feature_names": tuple(reversed(_FEATURE_NAMES))}, "feature schema"),
        ({"spec": SequenceWindowSpec(length=2, stride=2)}, "window spec"),
        ({"window_ids": ("other-window",)}, "window_ids"),
        ({"sequence_ids": ("other-run",)}, "sequence_ids"),
        ({"asset_ids": ("other-asset",)}, "asset_ids"),
        ({"partition_ids": ("test",)}, "partition_ids"),
        (
            {"aligned_source_observation_ids": ("run-a:observation-0",)},
            "aligned_source_observation_ids",
        ),
    ],
)
def test_reconstruction_scoring_rejects_schema_or_identity_drift(
    changes: dict[str, object],
    message: str,
) -> None:
    reconstructions = replace(_reconstructions(), **changes)  # type: ignore[arg-type]

    with pytest.raises(ReconstructionScoringError, match=message):
        score_reconstructions(_construction(), reconstructions)


def test_reconstruction_scoring_uses_model_consumed_input_values() -> None:
    reconstructions = replace(
        _reconstructions(),
        model_input_values=(((1.5, 2.0), (3.0, 4.0)),),
    )

    result = score_reconstructions(_construction(), reconstructions)

    assert result.feature_residuals == ((3.125, 0.5),)
    assert result.scores == (1.8125,)


def test_reconstruction_scores_reject_inconsistent_derived_values() -> None:
    construction = _construction()
    result = score_reconstructions(construction, _reconstructions())

    with pytest.raises(ReconstructionScoringError, match="mean feature residual"):
        replace(result, scores=(2.0,))
    with pytest.raises(ReconstructionScoringError, match="non-negative"):
        replace(result, feature_residuals=((-1.0, 4.0),), scores=(1.5,))
    with pytest.raises(ReconstructionScoringError, match="width"):
        replace(result, feature_residuals=((1.5,),))
