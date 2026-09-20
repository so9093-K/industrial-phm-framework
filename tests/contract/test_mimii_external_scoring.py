import ast
import json
from pathlib import Path

import pytest

from industrial_phm.experiments import (
    MIMII_EXTERNAL_CONFIGURATION_ID,
    MIMII_EXTERNAL_SCORE_SCHEMA_ID,
    MIMII_EXTERNAL_SECTIONS,
    MIMII_EXTERNAL_SPLIT_ID,
    MimiiExternalClipScore,
    MimiiExternalScoreResult,
    MimiiExternalScoringError,
    MimiiExternalSectionScores,
    get_mimii_development_configuration,
    get_mimii_external_section_configuration,
    iter_mimii_external_section_scopes,
    write_mimii_external_score_result,
)

_MODULE = Path("src/industrial_phm/experiments/mimii_external_scoring.py")
_REVISION = "a" * 40


def test_external_configuration_changes_only_scope_identity() -> None:
    """Freeze means representation, model and seed stay identical to development v1."""
    development = get_mimii_development_configuration()
    external = get_mimii_external_section_configuration("fan", "03")

    assert external.experiment_id.startswith(MIMII_EXTERNAL_CONFIGURATION_ID)
    assert external.split_id == MIMII_EXTERNAL_SPLIT_ID
    for axis in (
        "dataset_id",
        "fold_id",
        "fit_partition",
        "feature_set_id",
        "reference_strategy",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "random_seed",
    ):
        assert getattr(external, axis) == getattr(development, axis), axis
    assert tuple(external.selected_features) == tuple(development.selected_features)
    assert dict(external.model_parameters) == dict(development.model_parameters)


def test_external_scopes_cover_fifteen_evaluation_sections() -> None:
    scopes = iter_mimii_external_section_scopes()

    assert len(scopes) == 15
    assert {scope.section for scope in scopes} == set(MIMII_EXTERNAL_SECTIONS)
    assert {scope.source_group for scope in scopes} == {"eval"}


def test_external_configuration_rejects_development_sections() -> None:
    with pytest.raises(Exception, match="evaluation section"):
        get_mimii_external_section_configuration("fan", "00")


def test_scoring_module_has_no_ground_truth_reader() -> None:
    """The scoring path must not be able to open a ground-truth file at all."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)

    assert "csv" not in imported
    assert not any("ground_truth" in name for name in imported)
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in {"read_text", "read_bytes", "open"}
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(getattr(node, "value", None), ast.Name)
        and node.value.id in {"ground_truth", "labels"}
    )


def test_scoring_artifact_records_label_access_boundary(tmp_path: Path) -> None:
    result = MimiiExternalScoreResult(
        code_revision=_REVISION,
        verified_train_clip_count=15_150,
        verified_evaluation_clip_count=2,
        sections=(
            MimiiExternalSectionScores(
                experiment_id=f"{MIMII_EXTERNAL_CONFIGURATION_ID}--fan-section-03",
                machine_type="fan",
                section="03",
                source_train_clip_count=1_000,
                target_train_clip_count=3,
                model_fit_clip_count=1_003,
                scores=(
                    MimiiExternalClipScore(
                        source_file="eval/fan/source_test/section_03_source_test_0000.wav",
                        domain="source",
                        anomaly_score=0.25,
                    ),
                    MimiiExternalClipScore(
                        source_file="eval/fan/target_test/section_03_target_test_0000.wav",
                        domain="target",
                        anomaly_score=0.5,
                    ),
                ),
            ),
        ),
    )
    output = tmp_path / "score.json"

    write_mimii_external_score_result(result, output)
    first = output.read_text(encoding="utf-8")
    write_mimii_external_score_result(result, output)

    assert output.read_text(encoding="utf-8") == first
    document = json.loads(first)
    assert document["schema_id"] == MIMII_EXTERNAL_SCORE_SCHEMA_ID
    assert document["label_access"]["ground_truth_read"] is False
    assert document["provenance"]["split_id"] == MIMII_EXTERNAL_SPLIT_ID
    assert document["scored_clip_count"] == 2
    serialized = first.lower()
    assert "anomaly_score" in serialized
    for forbidden in ("clip_label", "condition_label", '"normal"', '"anomaly"'):
        assert forbidden not in serialized


def test_scoring_execution_requires_full_git_revision(tmp_path: Path) -> None:
    from industrial_phm.experiments.mimii_external_scoring import run_mimii_external_scoring

    with pytest.raises(MimiiExternalScoringError, match="full 40-character"):
        run_mimii_external_scoring(
            tmp_path, tmp_path, tmp_path / "out.json", code_revision="399afa9"
        )
