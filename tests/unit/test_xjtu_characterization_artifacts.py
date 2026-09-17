import csv
import json
from pathlib import Path

import pytest

from industrial_phm.experiments.xjtu_characterization import (
    XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_characterization_artifacts import (
    XjtuCharacterizationArtifactError,
    load_xjtu_characterization_artifacts,
)

_FEATURE_NAME = "feature.Horizontal_vibration_signals.rms"


def _write_summary(path: Path, *, partition: str = "train", test_included: bool = False) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_id": XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
                "dataset_id": "xjtu-sy",
                "feature_set_id": "vibration-statistical-v1",
                "experiment_scope": {
                    "split_id": "xjtu-sy-condition-stratified-5fold-v1",
                    "fold_id": "fold-1",
                    "partition": partition,
                    "test_partition_included": test_included,
                },
                "acquisition_count": 2,
                "bearing_run_count": 1,
                "operating_condition_count": 1,
                "feature_names": [_FEATURE_NAME],
            }
        ),
        encoding="utf-8",
    )


def _write_feature_table(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=[
                "feature_set_id",
                "asset_id",
                "meta.dataset_id",
                "meta.operating_condition",
                "meta.acquisition_index",
                "meta.source_file",
                _FEATURE_NAME,
            ],
        )
        writer.writeheader()
        for acquisition_index, value in ((1, 1.0), (2, 1.5)):
            writer.writerow(
                {
                    "feature_set_id": "vibration-statistical-v1",
                    "asset_id": "Bearing1_3",
                    "meta.dataset_id": "xjtu-sy",
                    "meta.operating_condition": "35Hz12kN",
                    "meta.acquisition_index": acquisition_index,
                    "meta.source_file": f"35Hz12kN/Bearing1_3/{acquisition_index}.csv",
                    _FEATURE_NAME: value,
                }
            )


def test_loads_matching_non_test_characterization_artifacts(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    feature_table_path = tmp_path / "features.csv"
    _write_summary(summary_path)
    _write_feature_table(feature_table_path)

    data = load_xjtu_characterization_artifacts(feature_table_path, summary_path)

    assert data.feature_set_id == "vibration-statistical-v1"
    assert data.fold_id == "fold-1"
    assert data.partition == "train"
    assert data.asset_ids == ("Bearing1_3",)
    assert data.operating_conditions == ("35Hz12kN",)
    assert data.records[1].acquisition_index == 2
    assert data.records[1].feature_values[_FEATURE_NAME] == pytest.approx(1.5)


def test_rejects_holdout_test_characterization_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    _write_summary(summary_path, partition="test", test_included=True)

    with pytest.raises(
        XjtuCharacterizationArtifactError,
        match="only permits train or validation",
    ):
        load_xjtu_characterization_artifacts(tmp_path / "unused.csv", summary_path)
