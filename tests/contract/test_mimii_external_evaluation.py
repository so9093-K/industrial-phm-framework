import ast
import json
from pathlib import Path

import pytest

from industrial_phm.experiments import (
    MIMII_EXTERNAL_CONFIGURATION_ID,
    MIMII_EXTERNAL_LABEL_MAPPING,
    MIMII_EXTERNAL_RESULT_SCHEMA_ID,
    MIMII_EXTERNAL_SPLIT_ID,
    MimiiExternalEvaluationError,
    run_mimii_external_evaluation,
)

_MODULE = Path("src/industrial_phm/experiments/mimii_external_evaluation.py")
_REVISION = "b" * 40
_MACHINES = ("fan", "gearbox", "pump", "slider", "valve")
_SECTIONS = ("03", "04", "05")


def _score_artifact(path: Path, *, clips: int = 4) -> Path:
    sections = []
    for machine in _MACHINES:
        for section in _SECTIONS:
            scores = []
            for domain in ("source", "target"):
                for index in range(clips):
                    scores.append(
                        {
                            "source_file": (
                                f"{machine}/{domain}_test/"
                                f"section_{section}_{domain}_test_{index:04d}.wav"
                            ),
                            "domain": domain,
                            "anomaly_score": 0.1 * index,
                        }
                    )
            sections.append(
                {
                    "experiment_id": (
                        f"{MIMII_EXTERNAL_CONFIGURATION_ID}--{machine}-section-{section}"
                    ),
                    "machine_type": machine,
                    "section": section,
                    "clip_scores": scores,
                }
            )
    path.write_text(
        json.dumps(
            {
                "schema_id": "mimii-due-domain-shift-external-score-v1",
                "label_access": {"ground_truth_read": False},
                "provenance": {
                    "code_revision": "c" * 40,
                    "split_id": MIMII_EXTERNAL_SPLIT_ID,
                },
                "section_models": sections,
            }
        ),
        encoding="utf-8",
    )
    return path


def _ground_truth(directory: Path, *, clips: int = 4) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for machine in _MACHINES:
        for section in _SECTIONS:
            for domain in ("source", "target"):
                rows = [
                    f"section_{section}_{domain}_test_{index:04d}.wav,{index % 2}"
                    for index in range(clips)
                ]
                (
                    directory / f"ground_truth_{machine}_section_{section}_{domain}_test.csv"
                ).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return directory


def test_evaluator_never_reads_audio_or_fits_a_model() -> None:
    """The evaluator must consume fixed scores, not recompute them."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "wave" not in imported
    assert not any("adapter" in name.lower() for name in imported)
    assert not any("fit_" in name for name in imported)
    assert not any("feature" in name.lower() for name in imported)


def test_label_mapping_follows_the_source_record() -> None:
    assert MIMII_EXTERNAL_LABEL_MAPPING == {"0": "normal", "1": "anomaly"}


def test_external_evaluation_binds_scores_and_labels_once(tmp_path: Path) -> None:
    artifact = _score_artifact(tmp_path / "score.json")
    truth = _ground_truth(tmp_path / "gt")
    output = tmp_path / "result.json"

    result = run_mimii_external_evaluation(artifact, truth, output, code_revision=_REVISION)

    assert len(result.strata) == 30
    assert result.scored_clip_count == 15 * 2 * 4
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema_id"] == MIMII_EXTERNAL_RESULT_SCHEMA_ID
    assert document["score_binding"]["score_artifact_sha256"] == result.score_artifact_sha256
    assert document["score_binding"]["score_artifact_code_revision"] == "c" * 40
    assert document["score_binding"]["label_mapping"] == {"0": "normal", "1": "anomaly"}
    assert document["evaluation"]["dcase_official_score"] is False
    assert document["evaluation"]["selection_or_threshold_calibration"] == "none"
    assert len(document["evaluation"]["strata"]) == 30


def test_external_evaluation_is_deterministic(tmp_path: Path) -> None:
    artifact = _score_artifact(tmp_path / "score.json")
    truth = _ground_truth(tmp_path / "gt")
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"

    run_mimii_external_evaluation(artifact, truth, first, code_revision=_REVISION)
    run_mimii_external_evaluation(artifact, truth, second, code_revision=_REVISION)

    assert first.read_bytes() == second.read_bytes()


def test_external_evaluation_rejects_a_scoring_run_that_read_labels(tmp_path: Path) -> None:
    artifact = _score_artifact(tmp_path / "score.json")
    document = json.loads(artifact.read_text(encoding="utf-8"))
    document["label_access"]["ground_truth_read"] = True
    artifact.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MimiiExternalEvaluationError, match="did not read ground truth"):
        run_mimii_external_evaluation(
            artifact,
            _ground_truth(tmp_path / "gt"),
            tmp_path / "out.json",
            code_revision=_REVISION,
        )


def test_external_evaluation_rejects_unknown_label_values(tmp_path: Path) -> None:
    truth = _ground_truth(tmp_path / "gt")
    target = truth / "ground_truth_fan_section_03_source_test.csv"
    target.write_text("section_03_source_test_0000.wav,anomaly\n", encoding="utf-8")

    with pytest.raises(MimiiExternalEvaluationError, match="unsupported ground-truth label"):
        run_mimii_external_evaluation(
            _score_artifact(tmp_path / "score.json"),
            truth,
            tmp_path / "out.json",
            code_revision=_REVISION,
        )


def test_external_evaluation_requires_full_git_revision(tmp_path: Path) -> None:
    with pytest.raises(MimiiExternalEvaluationError, match="full 40-character"):
        run_mimii_external_evaluation(
            tmp_path / "score.json", tmp_path, tmp_path / "out.json", code_revision="d1865dd"
        )
