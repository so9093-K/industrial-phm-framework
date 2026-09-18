from pathlib import Path
from types import SimpleNamespace

import pytest

import industrial_phm.cli as cli
from industrial_phm.experiments.result_inspection import (
    ExperimentInspection,
    ExperimentResultInspectionError,
)


def test_experiment_inspect_prints_read_only_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = tmp_path / "result.json"
    observed: list[Path] = []

    def fake_inspect(received_result: Path) -> ExperimentInspection:
        observed.append(received_result)
        return ExperimentInspection(schema_id="test-result-v1", status="consumed", stages=())

    monkeypatch.setattr(cli, "inspect_experiment_result", fake_inspect)

    exit_code = cli.main(["experiment", "inspect", str(result)])

    assert exit_code == 0
    assert observed == [result]
    assert capsys.readouterr().out == (
        "Experiment Result\n  Schema: test-result-v1\n  Status: consumed\n"
    )


def test_experiment_inspect_reports_invalid_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_inspect(result: Path) -> ExperimentInspection:
        raise ExperimentResultInspectionError(f"unsupported result: {result}")

    monkeypatch.setattr(cli, "inspect_experiment_result", fake_inspect)

    exit_code = cli.main(["experiment", "inspect", "unknown.json"])

    assert exit_code == 1
    assert "experiment result inspection failed: unsupported result" in capsys.readouterr().err


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


def test_experiment_cross_test_shows_effective_plan_and_pipeline_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "ims-result.json"
    revision = "d" * 40
    observed: dict[str, object] = {}

    def fake_cross_test(
        received_source: Path,
        received_output: Path,
        *,
        code_revision: str,
    ) -> SimpleNamespace:
        observed.update(
            source=received_source,
            output=received_output,
            code_revision=code_revision,
        )
        bearing_results = tuple(
            SimpleNamespace(
                asset_id=f"set-3-bearing-{number}",
                full_run_observation_count=4_448,
                acquisition_order_spearman_rho=0.25 * number,
                late_vs_middle_rank_probability=0.5 + 0.05 * number,
            )
            for number in range(1, 5)
        )
        return SimpleNamespace(
            complete_train_observation_count=3_936,
            reference_observation_count=3_936,
            model_fit_observation_count=3_936,
            scoring_observation_count=17_792,
            bearing_results=bearing_results,
            mean_bearing_acquisition_order_spearman_rho=0.625,
            mean_bearing_late_vs_middle_rank_probability=0.625,
            code_revision=code_revision,
        )

    monkeypatch.setattr(cli, "run_ims_cross_test_evaluation", fake_cross_test)

    exit_code = cli.main(
        [
            "experiment",
            "cross-test",
            "ims-bearings",
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
    }
    captured = capsys.readouterr().out
    assert "execution plan: IMS single-channel cross-test v1" in captured
    assert "train: set-2 complete / 984 acquisitions / 3936 bearing vectors" in captured
    assert (
        "evaluation: set-3 readme-documented / 4448 acquisitions / 17792 bearing vectors"
    ) in captured
    assert "excluded: set-1, set-3:archive-extension" in captured
    assert "selection/calibration: none" in captured
    assert "source validation: completed" in captured
    assert "populations: complete=3936 reference=3936 fit=3936 scoring=17792" in captured
    assert f"code_revision: {revision}" in captured
    assert f"result: {output}" in captured


def test_experiment_cross_test_rejects_non_ims_dataset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "experiment",
            "cross-test",
            "xjtu-sy",
            "--source",
            "source",
            "--output",
            "result.json",
            "--code-revision",
            "e" * 40,
        ]
    )

    assert exit_code == 2
    assert "cross-test evaluation is not implemented for xjtu-sy" in capsys.readouterr().err
