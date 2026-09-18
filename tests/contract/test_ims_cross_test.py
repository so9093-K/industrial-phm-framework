import json
from pathlib import Path

import pytest

from industrial_phm.experiments import (
    ImsCrossTestEvaluationError,
    evaluate_ims_cross_test,
    write_ims_cross_test_result,
)
from industrial_phm.experiments import ims_cross_test as module
from industrial_phm.features import VibrationFeatureVector, vibration_feature_names
from industrial_phm.models import AnomalyScores, ModelScoringInput

_FEATURE_NAMES = vibration_feature_names(("vibration",))


def _vectors(test_id: str, acquisition_count: int) -> tuple[VibrationFeatureVector, ...]:
    result: list[VibrationFeatureVector] = []
    for acquisition_index in range(1, acquisition_count + 1):
        for bearing_number in range(1, 5):
            result.append(
                VibrationFeatureVector(
                    feature_set_id="vibration-statistical-v1",
                    asset_id=f"{test_id}-bearing-{bearing_number}",
                    feature_names=_FEATURE_NAMES,
                    values=tuple(
                        float(acquisition_index + bearing_number + offset)
                        for offset in range(len(_FEATURE_NAMES))
                    ),
                    metadata={
                        "dataset_id": "ims-bearings",
                        "test_id": test_id,
                        "bearing_number": bearing_number,
                        "acquisition_index": acquisition_index,
                        "archive_scope": "readme-documented",
                        "rotational_speed_rpm": 2_000.0,
                        "radial_load_lb": 6_000.0,
                    },
                )
            )
    return tuple(result)


@pytest.fixture(scope="module")
def train_vectors() -> tuple[VibrationFeatureVector, ...]:
    return _vectors("set-2", 984)


@pytest.fixture(scope="module")
def evaluation_vectors() -> tuple[VibrationFeatureVector, ...]:
    return _vectors("set-3", 4_448)


class _AcquisitionOrderModel:
    def score(self, model_input: ModelScoringInput) -> AnomalyScores:
        scores = tuple(
            float(observation_id.rsplit("-", 1)[1])
            for observation_id in model_input.source_observation_ids
        )
        return AnomalyScores(
            experiment_id=model_input.experiment_id,
            source_observation_ids=model_input.source_observation_ids,
            scores=scores,
        )


class _ConstantModel:
    def score(self, model_input: ModelScoringInput) -> AnomalyScores:
        return AnomalyScores(
            experiment_id=model_input.experiment_id,
            source_observation_ids=model_input.source_observation_ids,
            scores=(1.0,) * model_input.observation_count,
        )


def test_ims_cross_test_records_fixed_population_and_stage_evidence(
    monkeypatch: pytest.MonkeyPatch,
    train_vectors: tuple[VibrationFeatureVector, ...],
    evaluation_vectors: tuple[VibrationFeatureVector, ...],
) -> None:
    monkeypatch.setattr(
        module,
        "fit_isolation_forest",
        lambda config, model_input: _AcquisitionOrderModel(),
    )

    result = evaluate_ims_cross_test(
        train_vectors,
        evaluation_vectors,
        code_revision="a" * 40,
        source_acquisition_count=9_464,
    )

    assert result.train_test_id == "set-2"
    assert result.evaluation_test_id == "set-3"
    assert result.evaluation_archive_scope == "readme-documented"
    assert result.complete_train_observation_count == 3_936
    assert result.reference_observation_count == 3_936
    assert result.model_fit_observation_count == 3_936
    assert result.scoring_observation_count == 17_792
    assert len(result.bearing_results) == 4
    for bearing in result.bearing_results:
        assert bearing.full_run_observation_count == 4_448
        assert bearing.middle_stage_observation_count == 1_483
        assert bearing.late_stage_observation_count == 1_482
        assert bearing.acquisition_order_spearman_rho == pytest.approx(1.0)
        assert bearing.late_vs_middle_rank_probability == pytest.approx(1.0)
    assert result.mean_bearing_acquisition_order_spearman_rho == pytest.approx(1.0)
    assert result.mean_bearing_late_vs_middle_rank_probability == pytest.approx(1.0)


def test_ims_cross_test_result_exposes_pipeline_transparency_sections(
    monkeypatch: pytest.MonkeyPatch,
    train_vectors: tuple[VibrationFeatureVector, ...],
    evaluation_vectors: tuple[VibrationFeatureVector, ...],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        module,
        "fit_isolation_forest",
        lambda config, model_input: _AcquisitionOrderModel(),
    )
    result = evaluate_ims_cross_test(
        train_vectors,
        evaluation_vectors,
        code_revision="b" * 40,
        source_acquisition_count=9_464,
    )
    output = tmp_path / "result.json"

    write_ims_cross_test_result(result, output)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["provenance"]["code_revision"] == "b" * 40
    assert document["source_scope"]["excluded"] == ["set-1", "set-3:archive-extension"]
    assert document["feature_schema"]["selected_feature_count"] == 8
    assert document["population_flow"] == {
        "complete_train_observation_count": 3_936,
        "model_fit_observation_count": 3_936,
        "reference_observation_count": 3_936,
        "scoring_observation_count": 17_792,
    }
    assert document["model"]["score_semantics"] == "higher-is-more-anomalous"
    assert document["evaluation"]["test_stage_segmentation"]["middle_count"] == 1_483
    assert "health-assessment" in document["capability_scope"]["unsupported_or_not_validated"]


def test_ims_cross_test_rejects_undefined_statistics(
    monkeypatch: pytest.MonkeyPatch,
    train_vectors: tuple[VibrationFeatureVector, ...],
    evaluation_vectors: tuple[VibrationFeatureVector, ...],
) -> None:
    monkeypatch.setattr(
        module,
        "fit_isolation_forest",
        lambda config, model_input: _ConstantModel(),
    )

    with pytest.raises(ImsCrossTestEvaluationError, match="undefined"):
        evaluate_ims_cross_test(
            train_vectors,
            evaluation_vectors,
            code_revision="c" * 40,
            source_acquisition_count=9_464,
        )


def test_ims_cross_test_requires_full_git_revision() -> None:
    with pytest.raises(ImsCrossTestEvaluationError, match="40-character"):
        evaluate_ims_cross_test((), (), code_revision="short", source_acquisition_count=9_464)
