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


def test_experiment_lstm_development_shows_plan_and_routes_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "lstm-result.json"
    revision = "f" * 40
    observed: dict[str, object] = {}

    def fake_run(
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
        return SimpleNamespace(
            preprocessing_fit_observation_count=3_246,
            reference_source_acquisition_count=1_084,
            reference_window_count=1_021,
            validation_window_count=2_797,
            training=SimpleNamespace(runtime="pytorch", runtime_version="2.14.0"),
            code_revision=code_revision,
        )

    monkeypatch.setattr(cli, "run_xjtu_lstm_development_evaluation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "lstm-development",
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
    }
    captured = capsys.readouterr().out
    assert "execution plan: XJTU LSTM retrospective development v1" in captured
    assert "evidence: retrospective-development-evidence" in captured
    assert "holdout test: excluded" in captured
    assert "fit=1021 windows" in captured
    assert "scoring=2797 windows" in captured
    assert f"code_revision: {revision}" in captured
    assert f"result: {output}" in captured


def test_experiment_rul_baseline_validation_routes_frozen_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "rul-baselines.json"
    revision = "7" * 40
    observed: dict[str, object] = {}
    verified: list[str] = []

    def fake_verify(revision_to_verify: str) -> None:
        verified.append(revision_to_verify)

    def fake_run(
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
        return SimpleNamespace(
            train_source_acquisition_count=3_246,
            validation_source_acquisition_count=2_818,
            age_evaluation=SimpleNamespace(
                mean_asset_mean_absolute_error=100.0,
                mean_asset_root_mean_squared_error=120.0,
                mean_asset_normalized_mean_absolute_error=0.2,
            ),
            feature_evaluation=SimpleNamespace(
                mean_asset_mean_absolute_error=80.0,
                mean_asset_root_mean_squared_error=95.0,
                mean_asset_normalized_mean_absolute_error=0.16,
            ),
            code_revision=code_revision,
        )

    monkeypatch.setattr(cli, "_verify_clean_git_revision", fake_verify)
    monkeypatch.setattr(cli, "run_xjtu_rul_baseline_validation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "rul-baseline-validation",
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
    assert verified == [revision]
    assert observed == {
        "source": source,
        "output": output,
        "code_revision": revision,
    }
    captured = capsys.readouterr().out
    assert "execution plan: XJTU RUL baseline validation v1" in captured
    assert "holdout test: excluded" in captured
    assert "train=3246 acquisitions validation=2818 acquisitions" in captured
    assert "age-only(full-run): mae=100.000000 rmse=120.000000 normalized_mae=0.200000" in captured
    assert "feature-ridge(full-run): mae=80.000000 rmse=95.000000 normalized_mae=0.160000" in captured
    assert f"code_revision: {revision}" in captured
    assert f"result: {output}" in captured


def test_experiment_rul_baseline_validation_rejects_non_xjtu_dataset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "experiment",
            "rul-baseline-validation",
            "ims-bearings",
            "--source",
            "source",
            "--output",
            "result.json",
            "--code-revision",
            "7" * 40,
        ]
    )

    assert exit_code == 2
    assert "RUL baseline validation is not implemented for ims-bearings" in (
        capsys.readouterr().err
    )


def test_experiment_rul_baseline_validation_stops_on_revision_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executed = False

    def fake_verify(_: str) -> None:
        raise ValueError("declared code revision does not match current Git HEAD")

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal executed
        executed = True
        raise AssertionError("execution must not start when revision verification fails")

    monkeypatch.setattr(cli, "_verify_clean_git_revision", fake_verify)
    monkeypatch.setattr(cli, "run_xjtu_rul_baseline_validation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "rul-baseline-validation",
            "xjtu-sy",
            "--source",
            str(tmp_path / "source"),
            "--output",
            str(tmp_path / "result.json"),
            "--code-revision",
            "7" * 40,
        ]
    )

    assert exit_code == 1
    assert executed is False
    assert "RUL baseline revision verification failed" in capsys.readouterr().err


def test_experiment_rul_validation_routes_three_model_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "rul-three-model.json"
    revision = "8" * 40
    observed: dict[str, object] = {}
    verified: list[str] = []

    def fake_verify(revision_to_verify: str) -> None:
        verified.append(revision_to_verify)

    def fake_run(
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
        age = SimpleNamespace(
            mean_asset_mean_absolute_error=100.0,
            mean_asset_root_mean_squared_error=120.0,
            mean_asset_normalized_mean_absolute_error=0.2,
        )
        feature = SimpleNamespace(
            mean_asset_mean_absolute_error=80.0,
            mean_asset_root_mean_squared_error=95.0,
            mean_asset_normalized_mean_absolute_error=0.16,
        )
        temporal = SimpleNamespace(
            mean_asset_mean_absolute_error=70.0,
            mean_asset_root_mean_squared_error=90.0,
            mean_asset_normalized_mean_absolute_error=0.14,
        )
        return SimpleNamespace(
            baseline_result=SimpleNamespace(
                train_source_acquisition_count=3_246,
                validation_source_acquisition_count=2_818,
                age_evaluation=age,
                feature_evaluation=feature,
            ),
            temporal_train_window_count=3_183,
            temporal_predictions=tuple(
                SimpleNamespace(observations=tuple(range(count))) for count in (154, 790, 1_853)
            ),
            temporal_evaluation=temporal,
            code_revision=code_revision,
        )

    monkeypatch.setattr(cli, "_verify_clean_git_revision", fake_verify)
    monkeypatch.setattr(cli, "run_xjtu_rul_three_model_validation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "rul-validation",
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
    assert verified == [revision]
    assert observed == {
        "source": source,
        "output": output,
        "code_revision": revision,
    }
    captured = capsys.readouterr().out
    assert "execution plan: XJTU RUL three-model validation v1" in captured
    assert "methods: age-only / feature-Ridge / 8-acquisition temporal LSTM" in captured
    assert "pairwise three-model deltas use acquisition 8..N common support" in captured
    assert "holdout test: excluded" in captured
    assert "temporal_fit=3183 windows temporal_validation_predictions=2797" in captured
    assert "age-only: mae=100.000000 rmse=120.000000 normalized_mae=0.200000" in captured
    assert "feature-ridge: mae=80.000000 rmse=95.000000 normalized_mae=0.160000" in captured
    assert "temporal-lstm(acq8..N): mae=70.000000 rmse=90.000000 normalized_mae=0.140000" in captured
    assert f"code_revision: {revision}" in captured
    assert f"result: {output}" in captured


def test_experiment_rul_validation_rejects_non_xjtu_dataset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "experiment",
            "rul-validation",
            "ims-bearings",
            "--source",
            "source",
            "--output",
            "result.json",
            "--code-revision",
            "8" * 40,
        ]
    )

    assert exit_code == 2
    assert "RUL three-model validation is not implemented for ims-bearings" in (
        capsys.readouterr().err
    )


def test_experiment_rul_validation_stops_on_revision_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executed = False

    def fake_verify(_: str) -> None:
        raise ValueError("declared code revision does not match current Git HEAD")

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal executed
        executed = True
        raise AssertionError("execution must not start when revision verification fails")

    monkeypatch.setattr(cli, "_verify_clean_git_revision", fake_verify)
    monkeypatch.setattr(cli, "run_xjtu_rul_three_model_validation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "rul-validation",
            "xjtu-sy",
            "--source",
            str(tmp_path / "source"),
            "--output",
            str(tmp_path / "result.json"),
            "--code-revision",
            "8" * 40,
        ]
    )

    assert exit_code == 1
    assert executed is False
    assert "RUL validation revision verification failed" in capsys.readouterr().err


def test_experiment_lstm_development_rejects_non_xjtu_dataset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "experiment",
            "lstm-development",
            "ims-bearings",
            "--source",
            "source",
            "--output",
            "result.json",
            "--code-revision",
            "f" * 40,
        ]
    )

    assert exit_code == 2
    assert "LSTM development evaluation is not implemented for ims-bearings" in (
        capsys.readouterr().err
    )


def test_experiment_mimii_development_shows_plan_and_routes_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "mimii-result.json"
    revision = "9" * 40
    observed: dict[str, object] = {}

    def fake_run(
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
        return SimpleNamespace(
            section_results=tuple(object() for _ in range(15)),
            domain_summaries=(
                SimpleNamespace(
                    scope_id="domain:source",
                    roc_auc_harmonic_mean=0.8,
                    partial_roc_auc_harmonic_mean=0.7,
                ),
                SimpleNamespace(
                    scope_id="domain:target",
                    roc_auc_harmonic_mean=0.6,
                    partial_roc_auc_harmonic_mean=0.5,
                ),
            ),
            overall_summary=SimpleNamespace(
                roc_auc_harmonic_mean=0.69,
                partial_roc_auc_harmonic_mean=0.59,
            ),
            mimii_domain_shift_summary=0.63,
            code_revision=code_revision,
        )

    verified: list[str] = []

    def fake_verify(revision_to_verify: str) -> None:
        verified.append(revision_to_verify)

    monkeypatch.setattr(cli, "_verify_clean_git_revision", fake_verify)
    monkeypatch.setattr(cli, "run_mimii_development_evaluation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "mimii-development",
            "mimii-due",
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
    assert verified == [revision]
    captured = capsys.readouterr().out
    assert "execution plan: MIMII DUE domain-shift development v1" in captured
    assert "5 machine types x 3 sections" in captured
    assert "labels: evaluator edge only" in captured
    assert "external evaluation: sections 03-05 excluded" in captured
    assert f"revision verification: clean tracked checkout @ {revision}" in captured
    assert "section_models: 15" in captured
    assert "source_domain: auc_hmean=0.800000 pauc_hmean=0.700000" in captured
    assert "target_domain: auc_hmean=0.600000 pauc_hmean=0.500000" in captured
    assert "mimii_domain_shift_summary: 0.630000" in captured
    assert f"code_revision: {revision}" in captured
    assert f"result: {output}" in captured


def test_verify_clean_git_revision_accepts_matching_clean_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    calls: list[tuple[str, ...]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> SimpleNamespace:
        assert check is True
        assert capture_output is True
        assert text is True
        calls.append(tuple(command))
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=revision + "\n")
        if command[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(stdout="")
        raise AssertionError(f"unexpected git command: {command}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli._verify_clean_git_revision(revision)

    assert calls == [
        ("git", "rev-parse", "HEAD"),
        ("git", "status", "--porcelain", "--untracked-files=no"),
    ]


def test_verify_clean_git_revision_rejects_declared_head_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared = "a" * 40
    observed = "b" * 40

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> SimpleNamespace:
        del check, capture_output, text
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=observed + "\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="does not match current Git HEAD"):
        cli._verify_clean_git_revision(declared)


def test_verify_clean_git_revision_rejects_dirty_tracked_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "c" * 40

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> SimpleNamespace:
        del check, capture_output, text
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=revision + "\n")
        return SimpleNamespace(stdout=" M README.md\n")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="tracked Git working tree is dirty"):
        cli._verify_clean_git_revision(revision)


def test_experiment_mimii_development_stops_before_execution_on_revision_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executed = False

    def fake_verify(_: str) -> None:
        raise ValueError("declared code revision does not match current Git HEAD")

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal executed
        executed = True
        raise AssertionError("execution must not start when revision verification fails")

    monkeypatch.setattr(cli, "_verify_clean_git_revision", fake_verify)
    monkeypatch.setattr(cli, "run_mimii_development_evaluation", fake_run)

    exit_code = cli.main(
        [
            "experiment",
            "mimii-development",
            "mimii-due",
            "--source",
            str(tmp_path / "source"),
            "--output",
            str(tmp_path / "result.json"),
            "--code-revision",
            "d" * 40,
        ]
    )

    assert exit_code == 1
    assert executed is False
    assert "revision verification failed" in capsys.readouterr().err


def test_experiment_mimii_development_rejects_non_mimii_dataset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "experiment",
            "mimii-development",
            "xjtu-sy",
            "--source",
            "source",
            "--output",
            "result.json",
            "--code-revision",
            "9" * 40,
        ]
    )

    assert exit_code == 2
    assert "MIMII development evaluation is not implemented for xjtu-sy" in (
        capsys.readouterr().err
    )
