from pathlib import Path
from types import SimpleNamespace

import pytest

import industrial_phm.cli as cli


def test_experiment_validate_routes_to_xjtu_fold_1_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "result.json"
    revision = "a" * 40
    observed: dict[str, object] = {}

    def fake_validate(
        received_source: Path,
        received_output: Path,
        *,
        code_revision: str,
        score_trajectory_dir: Path | None = None,
    ) -> SimpleNamespace:
        observed.update(
            source=received_source,
            output=received_output,
            code_revision=code_revision,
            score_trajectory_dir=score_trajectory_dir,
        )
        return SimpleNamespace(
            dataset_id="xjtu-sy",
            split_id="xjtu-sy-condition-stratified-5fold-v1",
            fold_id="fold-1",
            partition="validation",
            candidates=(object(), object(), object(), object()),
            selection_rule_id="selection-rule-v1",
            selected_experiment_id="selected-candidate-v2",
        )

    monkeypatch.setattr(cli, "run_xjtu_fold_1_validation", fake_validate)

    exit_code = cli.main(
        [
            "experiment",
            "validate",
            "xjtu-sy",
            "--source",
            str(source),
            "--output",
            str(output),
            "--code-revision",
            revision,
        ]
    )

    assert exit_code == 0
    assert observed == {
        "source": source,
        "output": output,
        "code_revision": revision,
        "score_trajectory_dir": None,
    }
    captured = capsys.readouterr().out
    assert "candidates: 4" in captured
    assert "selected_experiment_id: selected-candidate-v2" in captured
    assert f"result: {output}" in captured


def test_experiment_validate_rejects_unsupported_dataset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "experiment",
            "validate",
            "ims-bearings",
            "--source",
            "source",
            "--output",
            "result.json",
            "--code-revision",
            "a" * 40,
        ]
    )

    assert exit_code == 2
    assert "not implemented for ims-bearings" in capsys.readouterr().err


def test_experiment_validate_forwards_optional_score_trajectory_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trajectory_dir = tmp_path / "trajectories"
    observed: dict[str, object] = {}

    def fake_validate(
        received_source: Path,
        received_output: Path,
        *,
        code_revision: str,
        score_trajectory_dir: Path | None = None,
    ) -> SimpleNamespace:
        observed["score_trajectory_dir"] = score_trajectory_dir
        return SimpleNamespace(
            dataset_id="xjtu-sy",
            split_id="xjtu-sy-condition-stratified-5fold-v1",
            fold_id="fold-1",
            partition="validation",
            candidates=(object(),),
            selection_rule_id="selection-rule-v1",
            selected_experiment_id="selected-candidate-v2",
        )

    monkeypatch.setattr(cli, "run_xjtu_fold_1_validation", fake_validate)

    exit_code = cli.main(
        [
            "experiment",
            "validate",
            "xjtu-sy",
            "--source",
            str(tmp_path / "source"),
            "--output",
            str(tmp_path / "result.json"),
            "--code-revision",
            "a" * 40,
            "--score-trajectory-dir",
            str(trajectory_dir),
        ]
    )

    assert exit_code == 0
    assert observed == {"score_trajectory_dir": trajectory_dir}
    assert f"score_trajectory_dir: {trajectory_dir}" in capsys.readouterr().out
