import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_REFERENCE_COMPARISON_SCHEMA_ID,
    XJTU_REFERENCE_DECISION_RULE_ID,
    ReferenceStrategy,
    XjtuBearingReferenceEvidence,
    XjtuReferenceComparisonError,
    XjtuReferenceComparisonResult,
    XjtuReferenceHypothesisResult,
    early_third_length,
    evaluate_xjtu_reference_hypotheses,
    get_xjtu_reference_hypotheses,
    get_xjtu_reference_split,
    late_vs_middle_rank_probability,
    lifecycle_segment,
    select_xjtu_reference_hypothesis,
    write_xjtu_reference_comparison_result,
)
from industrial_phm.features import VibrationFeatureVector

_CODE_REVISION = "b" * 40
_FOLD_1 = "fold-1"


def _hypothesis(
    reference_strategy: ReferenceStrategy,
    mean_probability: float | None,
    *,
    bearing_probability: float | None = 0.5,
) -> XjtuReferenceHypothesisResult:
    return XjtuReferenceHypothesisResult(
        experiment_id=f"candidate-{reference_strategy.value}",
        reference_strategy=reference_strategy.value,
        complete_train_observation_count=3246,
        reference_observation_count=1084,
        model_fit_observation_count=1084,
        bearing_results=(
            XjtuBearingReferenceEvidence(
                asset_id="Bearing3_2",
                operating_condition="40Hz10kN",
                full_run_observation_count=2496,
                middle_third_observation_count=832,
                late_third_observation_count=832,
                late_vs_middle_rank_probability=bearing_probability,
                acquisition_order_spearman_rho=-0.6,
            ),
        ),
        mean_bearing_late_vs_middle_rank_probability=mean_probability,
        mean_bearing_acquisition_order_spearman_rho=-0.6,
    )


def test_packaged_hypotheses_vary_reference_strategy_only() -> None:
    configs = get_xjtu_reference_hypotheses()

    assert len(configs) == 2
    assert {config.reference_strategy for config in configs} == {
        ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
    }
    baseline, alternative = configs
    for field_name in (
        "selected_features",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "random_seed",
        "fold_id",
    ):
        assert getattr(baseline, field_name) == getattr(alternative, field_name)
    assert dict(baseline.model_parameters) == dict(alternative.model_parameters)
    assert all(config.fold_id == _FOLD_1 for config in configs)


def test_early_third_reference_matches_the_lifecycle_third_boundary() -> None:
    for run_length in (1, 2, 3, 42, 114, 371, 1515, 2496):
        leading = sum(
            1
            for position in range(run_length)
            if lifecycle_segment(position, run_length) == "early_third"
        )
        assert leading == early_third_length(run_length) == math.ceil(run_length / 3)


def test_rank_probability_matches_its_pairwise_definition() -> None:
    middle = (1.0, 2.0, 2.0)
    late = (2.0, 3.0)
    expected = sum(
        1.0 if right > left else 0.5 if right == left else 0.0 for left in middle for right in late
    ) / (len(middle) * len(late))

    assert late_vs_middle_rank_probability(middle, late) == pytest.approx(expected)
    assert late_vs_middle_rank_probability((), late) is None
    assert late_vs_middle_rank_probability(middle, ()) is None


def test_alternative_reference_needs_a_strict_improvement() -> None:
    baseline = _hypothesis(ReferenceStrategy.ALL_TRAIN_OBSERVATIONS, 0.60)

    better = select_xjtu_reference_hypothesis(
        (baseline, _hypothesis(ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD, 0.61))
    )
    tied = select_xjtu_reference_hypothesis(
        (baseline, _hypothesis(ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD, 0.60))
    )
    worse = select_xjtu_reference_hypothesis(
        (baseline, _hypothesis(ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD, 0.59))
    )

    assert better.reference_strategy == ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD.value
    assert tied.reference_strategy == ReferenceStrategy.ALL_TRAIN_OBSERVATIONS.value
    assert worse.reference_strategy == ReferenceStrategy.ALL_TRAIN_OBSERVATIONS.value


def test_undefined_rank_probability_blocks_the_decision() -> None:
    with pytest.raises(XjtuReferenceComparisonError, match="defined late_vs_middle"):
        select_xjtu_reference_hypothesis(
            (
                _hypothesis(ReferenceStrategy.ALL_TRAIN_OBSERVATIONS, 0.6),
                _hypothesis(
                    ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
                    None,
                    bearing_probability=None,
                ),
            )
        )


def test_comparison_execution_requires_full_git_revision_before_model_work() -> None:
    with pytest.raises(XjtuReferenceComparisonError, match="full 40-character"):
        evaluate_xjtu_reference_hypotheses(
            (),
            (),
            code_revision="cca849e",
            source_acquisition_count=0,
        )


def test_comparison_result_writes_deterministic_population_provenance(tmp_path: Path) -> None:
    baseline = _hypothesis(ReferenceStrategy.ALL_TRAIN_OBSERVATIONS, 0.60)
    alternative = _hypothesis(ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD, 0.61)
    result = XjtuReferenceComparisonResult(
        code_revision=_CODE_REVISION,
        dataset_id="xjtu-sy",
        split_id="xjtu-sy-condition-stratified-5fold-v1",
        fold_id=_FOLD_1,
        partition="validation",
        source_acquisition_count=9216,
        hypotheses=(baseline, alternative),
        selected_experiment_id=alternative.experiment_id,
        selected_reference_strategy=alternative.reference_strategy,
    )
    output = tmp_path / "comparison.json"

    write_xjtu_reference_comparison_result(result, output)
    first = output.read_text(encoding="utf-8")
    write_xjtu_reference_comparison_result(result, output)

    assert output.read_text(encoding="utf-8") == first
    document = json.loads(first)
    assert document["schema_id"] == XJTU_REFERENCE_COMPARISON_SCHEMA_ID
    assert document["decision_rule"]["id"] == XJTU_REFERENCE_DECISION_RULE_ID
    assert document["selected_reference_strategy"] == alternative.reference_strategy
    recorded = document["hypotheses"][0]
    bearing = recorded["validation_bearings"][0]
    assert bearing["full_run_observation_count"] == 2496
    assert bearing["middle_third_observation_count"] == 832
    assert bearing["late_third_observation_count"] == 832
    assert "observation_count" not in bearing
    assert recorded["complete_train_observation_count"] == 3246
    assert recorded["reference_observation_count"] == 1084
    assert recorded["model_fit_observation_count"] == 1084


def test_reference_comparison_never_reaches_holdout_or_other_folds() -> None:
    split = get_xjtu_reference_split()
    fold_1 = next(fold for fold in split.folds if fold.fold_id == _FOLD_1)
    closed_assets = set(fold_1.test)
    for fold in split.folds:
        if fold.fold_id == _FOLD_1:
            continue
        closed_assets |= set(fold.validation) - set(fold_1.train) - set(fold_1.validation)

    opened = set(fold_1.train) | set(fold_1.validation)

    assert all(config.fold_id == _FOLD_1 for config in get_xjtu_reference_hypotheses())
    assert not (opened & set(fold_1.test))
    assert closed_assets == {"Bearing1_1", "Bearing2_1", "Bearing3_1"}


def _fold_1_vectors(assets: tuple[str, ...]) -> tuple[VibrationFeatureVector, ...]:
    config = get_xjtu_reference_hypotheses()[0]
    feature_names = tuple(config.selected_features)
    vectors: list[VibrationFeatureVector] = []
    for asset_id in assets:
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1):
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=config.feature_set_id,
                    asset_id=asset_id,
                    feature_names=feature_names,
                    values=tuple(
                        float(acquisition_index + position)
                        for position in range(len(feature_names))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "operating_condition": f"condition-{asset_id[len('Bearing')]}",
                        "acquisition_index": acquisition_index,
                    },
                )
            )
    return tuple(vectors)


def test_early_third_reference_shrinks_only_the_reference_population() -> None:
    fold = next(item for item in get_xjtu_reference_split().folds if item.fold_id == _FOLD_1)
    result = evaluate_xjtu_reference_hypotheses(
        _fold_1_vectors(fold.train),
        _fold_1_vectors(fold.validation),
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
    )

    by_strategy = {item.reference_strategy: item for item in result.hypotheses}
    baseline = by_strategy[ReferenceStrategy.ALL_TRAIN_OBSERVATIONS.value]
    alternative = by_strategy[ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD.value]
    expected_early = sum(
        early_third_length(get_xjtu_expected_acquisition_count(asset_id)) for asset_id in fold.train
    )

    assert baseline.complete_train_observation_count == 3246
    assert baseline.reference_observation_count == 3246
    assert baseline.model_fit_observation_count == 3246
    assert alternative.complete_train_observation_count == 3246
    assert alternative.reference_observation_count == expected_early
    assert alternative.model_fit_observation_count == expected_early
    assert expected_early < 3246


def test_comparison_rejects_a_grid_that_varies_more_than_the_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from industrial_phm.experiments import xjtu_reference_comparison as module

    baseline, alternative = get_xjtu_reference_hypotheses()
    monkeypatch.setattr(
        module,
        "load_packaged_xjtu_experiment_configs",
        lambda _: (baseline, replace(alternative, random_seed=7)),
    )
    module.get_xjtu_reference_hypotheses.cache_clear()

    with pytest.raises(XjtuReferenceComparisonError, match="only vary reference_strategy"):
        module.get_xjtu_reference_hypotheses()

    module.get_xjtu_reference_hypotheses.cache_clear()
