from pathlib import Path
from types import SimpleNamespace

import pytest

import industrial_phm.cli as cli
import industrial_phm.commands.feature as feature_commands


def test_feature_characterize_routes_to_xjtu_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    output_dir = tmp_path / "artifacts"
    observed: dict[str, object] = {}

    def fake_characterize(
        received_source: Path,
        received_output_dir: Path,
        *,
        fold_id: str,
        partition: str,
    ) -> SimpleNamespace:
        observed.update(
            source=received_source,
            output_dir=received_output_dir,
            fold_id=fold_id,
            partition=partition,
        )
        return SimpleNamespace(
            feature_set_id="vibration-statistical-v1",
            split_id="xjtu-sy-condition-stratified-5fold-v1",
            fold_id=fold_id,
            partition=partition,
            acquisition_count=3,
            bearing_run_count=1,
            operating_condition_count=1,
            feature_table_path=received_output_dir / "features.csv",
            summary_path=received_output_dir / "summary.json",
        )

    monkeypatch.setattr(feature_commands, "characterize_xjtu_source", fake_characterize)

    exit_code = cli.main(
        [
            "feature",
            "characterize",
            "xjtu-sy",
            "--source",
            str(source),
            "--output-dir",
            str(output_dir),
            "--fold-id",
            "fold-1",
            "--partition",
            "train",
        ]
    )

    assert exit_code == 0
    assert observed == {
        "source": source,
        "output_dir": output_dir,
        "fold_id": "fold-1",
        "partition": "train",
    }
    output = capsys.readouterr().out
    assert "feature_set_id: vibration-statistical-v1" in output
    assert f"feature_table: {output_dir / 'features.csv'}" in output


def test_feature_characterize_rejects_holdout_test_partition() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(
            [
                "feature",
                "characterize",
                "xjtu-sy",
                "--source",
                "source",
                "--output-dir",
                "artifacts",
                "--fold-id",
                "fold-1",
                "--partition",
                "test",
            ]
        )

    assert error.value.code == 2
