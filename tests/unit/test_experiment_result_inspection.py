import json
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.experiments.result_inspection import (
    ExperimentResultInspectionError,
    inspect_experiment_result,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_XJTU_RESULT = _RESULTS / "xjtu-sy-iforest-fold-1-holdout-v1.json"
_IMS_RESULT = _RESULTS / "ims-bearings-iforest-single-channel-cross-test-v1.json"
_STAGES = (
    "Source",
    "Canonical",
    "Feature",
    "Preprocessing",
    "Reference",
    "Population",
    "Model",
    "Scoring",
    "Evaluation",
    "Capability",
    "Provenance",
)


def test_xjtu_holdout_inspection_resolves_effective_pipeline() -> None:
    summary = inspect_experiment_result(_XJTU_RESULT)

    assert _stage_positions(summary) == sorted(_stage_positions(summary))
    assert "Schema: xjtu-fold-1-holdout-result-v1" in summary
    assert "Status: consumed" in summary
    assert "Cardinality: 1 acquisition CSV -> 1 two-channel bearing observation" in summary
    assert "Selected features (16):" in summary
    assert "Train observations: 3246" in summary
    assert "Reference-eligible observations: 1084" in summary
    assert "Model-fit observations: 1084" in summary
    assert "Sampling policy: acquisition-uniform-v1" in summary
    assert "Holdout scoring observations: 3152" in summary
    assert "n_estimators=256" in summary
    assert "Score semantics: higher-is-more-anomalous" in summary
    assert "Unsupported: thresholded-state-detection" in summary
    assert "Declared code revision: f079f9341401f68a6a0428156773129eb242635e" in summary
    assert "Checkout attestation: unavailable" in summary


def test_ims_cross_test_inspection_exposes_source_to_observation_cardinality() -> None:
    summary = inspect_experiment_result(_IMS_RESULT)

    assert _stage_positions(summary) == sorted(_stage_positions(summary))
    assert "Schema: ims-single-channel-cross-test-result-v1" in summary
    assert "Train scope: set-2 complete / 984 files" in summary
    assert "Evaluation scope: set-3 readme-documented / 4448 files" in summary
    assert "Excluded: set-1, set-3:archive-extension" in summary
    assert "Cardinality: 1 acquisition file -> 4 bearing observations" in summary
    assert "Train conversion: 984 files -> 3936 observations" in summary
    assert "Evaluation conversion: 4448 files -> 17792 observations" in summary
    assert "Selected features (8):" in summary
    assert "Sampling policy: acquisition-uniform-v1" in summary
    assert "Scope: one-time-cross-test-evaluation" in summary
    assert "Aggregation: four-bearing-equal-weight-mean" in summary
    assert "Declared code revision: 37e876da301f13acee4081178b4cb33bfa5cc415" in summary


def test_inspection_rejects_unknown_schema(tmp_path: Path) -> None:
    result = tmp_path / "unknown.json"
    result.write_text('{"schema_id": "generic-result-v1"}\n', encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match=r"unsupported.*generic-result-v1"):
        inspect_experiment_result(result)


def test_inspection_rejects_malformed_json(tmp_path: Path) -> None:
    result = tmp_path / "malformed.json"
    result.write_text("{", encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="invalid result JSON"):
        inspect_experiment_result(result)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("experiment_id", "drifted-experiment", "experiment_id does not match"),
        ("model_fit_observation_count", 1_083, "model fit and reference observation counts"),
    ),
)
def test_xjtu_inspection_rejects_protocol_drift(
    tmp_path: Path,
    field: str,
    replacement: str | int,
    message: str,
) -> None:
    document = _read_object(_XJTU_RESULT)
    document[field] = replacement
    result = tmp_path / "drifted-xjtu.json"
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match=message):
        inspect_experiment_result(result)


def test_ims_inspection_rejects_population_drift(tmp_path: Path) -> None:
    document = _read_object(_IMS_RESULT)
    population = cast(dict[str, object], document["population_flow"])
    population["scoring_observation_count"] = 17_791
    result = tmp_path / "drifted-ims.json"
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="scoring population"):
        inspect_experiment_result(result)


def _stage_positions(summary: str) -> list[int]:
    return [summary.index(f"\n{stage}\n") for stage in _STAGES]


def _read_object(path: Path) -> dict[str, object]:
    value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise AssertionError("test fixture must be a JSON object")
    return cast(dict[str, object], value)
