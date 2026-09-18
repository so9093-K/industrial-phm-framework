import pytest

from industrial_phm.experiments import (
    XjtuDevelopmentEvaluationError,
    evaluate_xjtu_development_scores,
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_split,
)
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import AnomalyScores


def _config():
    return get_xjtu_isolation_forest_candidates()[0]


def _validation_vectors():
    config = _config()
    assets = get_xjtu_reference_split().folds[0].validation
    counts = (2, 3, 5)
    vectors: list[VibrationFeatureVector] = []
    for asset_id, count in zip(assets, counts, strict=True):
        condition = f"condition-{asset_id[len('Bearing')]}"
        for acquisition_index in range(1, count + 1):
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=config.feature_set_id,
                    asset_id=asset_id,
                    feature_names=("feature.placeholder",),
                    values=(float(acquisition_index),),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "operating_condition": condition,
                        "acquisition_index": acquisition_index,
                    },
                )
            )
    return tuple(vectors)


def _scores(vectors, signs):
    config = _config()
    source_observation_ids: list[str] = []
    scores: list[float] = []
    for vector in vectors:
        acquisition_index = vector.metadata["acquisition_index"]
        assert isinstance(acquisition_index, int)
        source_observation_ids.append(
            f"{vector.asset_id}:acquisition-{acquisition_index}"
        )
        scores.append(signs[vector.asset_id] * float(acquisition_index))
    return AnomalyScores(
        experiment_id=config.experiment_id,
        source_observation_ids=tuple(source_observation_ids),
        scores=tuple(scores),
    )


def test_xjtu_development_evaluation_is_bearing_first_and_equal_weighted() -> None:
    config = _config()
    vectors = _validation_vectors()
    assets = get_xjtu_reference_split().folds[0].validation
    signs = {
        assets[0]: 1.0,
        assets[1]: 1.0,
        assets[2]: -1.0,
    }

    result = evaluate_xjtu_development_scores(
        config,
        vectors,
        _scores(vectors, signs),
    )

    assert result.partition == "validation"
    assert result.experiment_id == config.experiment_id
    assert result.fold_id == "fold-1"
    by_asset = {item.asset_id: item for item in result.bearing_results}
    assert by_asset[assets[0]].acquisition_order_spearman_rho == pytest.approx(1.0)
    assert by_asset[assets[1]].acquisition_order_spearman_rho == pytest.approx(1.0)
    assert by_asset[assets[2]].acquisition_order_spearman_rho == pytest.approx(-1.0)
    assert result.mean_bearing_acquisition_order_spearman_rho == pytest.approx(1.0 / 3.0)

    observation_counts = {item.observation_count for item in result.bearing_results}
    assert len(observation_counts) > 1


def test_xjtu_development_evaluation_keeps_constant_score_correlation_undefined() -> None:
    config = _config()
    vectors = _validation_vectors()
    assets = get_xjtu_reference_split().folds[0].validation
    source_ids = []
    scores = []
    for vector in vectors:
        acquisition_index = vector.metadata["acquisition_index"]
        assert isinstance(acquisition_index, int)
        source_ids.append(f"{vector.asset_id}:acquisition-{acquisition_index}")
        scores.append(
            0.0 if vector.asset_id == assets[0] else float(acquisition_index)
        )

    result = evaluate_xjtu_development_scores(
        config,
        vectors,
        AnomalyScores(
            experiment_id=config.experiment_id,
            source_observation_ids=tuple(source_ids),
            scores=tuple(scores),
        ),
    )

    by_asset = {item.asset_id: item for item in result.bearing_results}
    assert by_asset[assets[0]].acquisition_order_spearman_rho is None
    assert result.mean_bearing_acquisition_order_spearman_rho is None


def test_xjtu_development_evaluation_rejects_score_identity_drift() -> None:
    config = _config()
    vectors = _validation_vectors()
    scores = _scores(
        vectors,
        {asset_id: 1.0 for asset_id in get_xjtu_reference_split().folds[0].validation},
    )
    invalid_scores = AnomalyScores(
        experiment_id=config.experiment_id,
        source_observation_ids=(*scores.source_observation_ids[:-1], "unexpected"),
        scores=scores.scores,
    )

    with pytest.raises(XjtuDevelopmentEvaluationError, match="align exactly"):
        evaluate_xjtu_development_scores(config, vectors, invalid_scores)


def test_xjtu_development_evaluation_rejects_non_validation_scope() -> None:
    config = _config()
    vectors = _validation_vectors()
    missing_asset = get_xjtu_reference_split().folds[0].validation[0]
    partial_vectors = tuple(vector for vector in vectors if vector.asset_id != missing_asset)
    scores = _scores(
        partial_vectors,
        {asset_id: 1.0 for asset_id in get_xjtu_reference_split().folds[0].validation},
    )

    with pytest.raises(XjtuDevelopmentEvaluationError, match="validation bearings"):
        evaluate_xjtu_development_scores(config, partial_vectors, scores)
