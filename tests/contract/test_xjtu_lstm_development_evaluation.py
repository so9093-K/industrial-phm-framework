from dataclasses import replace

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    XJTU_LSTM_SEQUENCE_SPEC,
    XjtuLstmDevelopmentEvaluationError,
    evaluate_xjtu_lstm_development_scores,
    get_xjtu_lstm_development_configuration,
    get_xjtu_reference_split,
)
from industrial_phm.experiments.score_statistics import late_vs_middle_rank_probability
from industrial_phm.experiments.xjtu_lifecycle import (
    LATE_THIRD,
    MIDDLE_THIRD,
    lifecycle_segment,
)
from industrial_phm.models import ReconstructionScores


def _scores(
    score_value,
) -> ReconstructionScores:
    config = get_xjtu_lstm_development_configuration()
    assets = get_xjtu_reference_split().folds[0].validation
    feature_names = tuple(config.selected_features)

    window_ids: list[str] = []
    sequence_ids: list[str] = []
    asset_ids: list[str] = []
    partition_ids: list[str] = []
    source_ids: list[str] = []
    positions: list[int] = []
    values: list[float] = []
    residuals: list[tuple[float, ...]] = []

    for asset_index, asset_id in enumerate(assets):
        source_count = get_xjtu_expected_acquisition_count(asset_id)
        for position in range(XJTU_LSTM_SEQUENCE_SPEC.length, source_count + 1):
            value = float(score_value(asset_index, asset_id, position, source_count))
            window_ids.append(f"{asset_id}:window-{position}")
            sequence_ids.append(asset_id)
            asset_ids.append(asset_id)
            partition_ids.append("validation")
            source_ids.append(f"{asset_id}:acquisition-{position}")
            positions.append(position)
            values.append(value)
            residuals.append((value,) * len(feature_names))

    return ReconstructionScores(
        experiment_id=XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
        feature_set_id=config.feature_set_id,
        feature_names=feature_names,
        spec=XJTU_LSTM_SEQUENCE_SPEC,
        window_ids=tuple(window_ids),
        sequence_ids=tuple(sequence_ids),
        asset_ids=tuple(asset_ids),
        partition_ids=tuple(partition_ids),
        aligned_source_observation_ids=tuple(source_ids),
        aligned_source_positions=tuple(positions),
        scores=tuple(values),
        feature_residuals=tuple(residuals),
    )


def test_xjtu_lstm_evaluation_preserves_full_run_lifecycle_and_bearing_weight() -> None:
    scores = _scores(
        lambda asset_index, _asset_id, position, _source_count: (
            float(position) if asset_index != 0 else (10.0 if position in (109, 110) else 0.0)
        )
    )

    result = evaluate_xjtu_lstm_development_scores(scores)

    assert result.partition == "validation"
    assert result.experiment_id == XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID
    assert result.fold_id == "fold-1"
    assert tuple(item.asset_id for item in result.bearing_results) == (
        get_xjtu_reference_split().folds[0].validation
    )

    first = result.bearing_results[0]
    first_count = get_xjtu_expected_acquisition_count(first.asset_id)
    middle_scores = tuple(
        score
        for position, score in zip(
            scores.aligned_source_positions[: first.score_window_count],
            scores.scores[: first.score_window_count],
            strict=True,
        )
        if lifecycle_segment(position - 1, first_count) == MIDDLE_THIRD
    )
    late_scores = tuple(
        score
        for position, score in zip(
            scores.aligned_source_positions[: first.score_window_count],
            scores.scores[: first.score_window_count],
            strict=True,
        )
        if lifecycle_segment(position - 1, first_count) == LATE_THIRD
    )
    assert first.late_vs_middle_rank_probability == pytest.approx(
        late_vs_middle_rank_probability(middle_scores, late_scores)
    )

    for bearing in result.bearing_results:
        source_count = get_xjtu_expected_acquisition_count(bearing.asset_id)
        assert bearing.source_acquisition_count == source_count
        assert bearing.score_window_count == source_count - 7
        assert bearing.dropped_prefix_count == 7


def test_xjtu_lstm_evaluation_equal_weights_feature_residuals_across_bearings() -> None:
    result = evaluate_xjtu_lstm_development_scores(
        _scores(
            lambda asset_index, _asset_id, position, _source_count: (
                asset_index + 1 + position / 100_000.0
            )
        )
    )

    expected = sum(item.mean_feature_residuals[0] for item in result.bearing_results) / 3
    assert result.mean_bearing_feature_residuals[0] == pytest.approx(expected)
    assert result.mean_bearing_acquisition_order_spearman_rho == pytest.approx(1.0)
    assert result.mean_bearing_late_vs_middle_rank_probability == pytest.approx(1.0)


def test_xjtu_lstm_evaluation_rejects_undefined_statistic() -> None:
    scores = _scores(lambda _asset_index, _asset_id, _position, _source_count: 1.0)

    with pytest.raises(XjtuLstmDevelopmentEvaluationError, match="statistic is undefined"):
        evaluate_xjtu_lstm_development_scores(scores)


def test_xjtu_lstm_evaluation_rejects_shifted_score_coverage() -> None:
    scores = _scores(lambda _asset_index, _asset_id, position, _source_count: float(position))
    first_asset = scores.asset_ids[0]
    invalid = replace(
        scores,
        aligned_source_observation_ids=(
            f"{first_asset}:acquisition-7",
            *scores.aligned_source_observation_ids[1:],
        ),
        aligned_source_positions=(7, *scores.aligned_source_positions[1:]),
    )

    with pytest.raises(
        XjtuLstmDevelopmentEvaluationError,
        match="right-edge score coverage",
    ):
        evaluate_xjtu_lstm_development_scores(invalid)
