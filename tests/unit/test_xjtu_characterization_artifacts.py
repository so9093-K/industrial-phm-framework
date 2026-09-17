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
_SECOND_FEATURE_NAME = "feature.Horizontal_vibration_signals.standard_deviation"


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
                "feature_names": [_FEATURE_NAME, _SECOND_FEATURE_NAME],
                "run_length_imbalance": {
                    "min_acquisitions": 2,
                    "max_acquisitions": 2,
                    "median_acquisitions": 2.0,
                    "max_to_min_ratio": 1.0,
                },
                "correlations": {
                    "global": [
                        {
                            "left": _FEATURE_NAME,
                            "right": _SECOND_FEATURE_NAME,
                            "pearson": 1.0,
                            "spearman": 1.0,
                        }
                    ],
                    "by_condition": {
                        "35Hz12kN": [
                            {
                                "left": _FEATURE_NAME,
                                "right": _SECOND_FEATURE_NAME,
                                "pearson": 1.0,
                                "spearman": 1.0,
                            }
                        ]
                    },
                },
                "lifecycle_segments": {
                    "runs": [
                        {
                            "asset_id": "Bearing1_3",
                            "operating_condition": "35Hz12kN",
                            "acquisition_count": 2,
                            "segments": {
                                "early_third": {
                                    "acquisition_count": 1,
                                    "feature_means": {
                                        _FEATURE_NAME: 1.0,
                                        _SECOND_FEATURE_NAME: 0.9,
                                    },
                                },
                                "middle_third": {
                                    "acquisition_count": 1,
                                    "feature_means": {
                                        _FEATURE_NAME: 1.5,
                                        _SECOND_FEATURE_NAME: 1.4,
                                    },
                                },
                                "late_third": {
                                    "acquisition_count": 0,
                                    "feature_means": {
                                        _FEATURE_NAME: None,
                                        _SECOND_FEATURE_NAME: None,
                                    },
                                },
                            },
                        }
                    ]
                },
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
                _SECOND_FEATURE_NAME,
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
                    _SECOND_FEATURE_NAME: value - 0.1,
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
    assert data.records[1].values[0] == pytest.approx(1.5)
    assert data.run_length_summary.max_to_min_ratio == pytest.approx(1.0)
    assert data.correlations_for(None)[0].pearson == pytest.approx(1.0)
    assert data.correlations_for("35Hz12kN")[0].spearman == pytest.approx(1.0)
    assert data.lifecycle_runs[0].early_means[0] == pytest.approx(1.0)
    assert data.lifecycle_runs[0].late_means[0] is None


def test_rejects_holdout_test_characterization_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    _write_summary(summary_path, partition="test", test_included=True)

    with pytest.raises(
        XjtuCharacterizationArtifactError,
        match="only permits train or validation",
    ):
        load_xjtu_characterization_artifacts(tmp_path / "unused.csv", summary_path)


def test_rejects_lifecycle_scope_that_differs_from_feature_table(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    feature_table_path = tmp_path / "features.csv"
    _write_summary(summary_path)
    _write_feature_table(feature_table_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["lifecycle_segments"]["runs"][0]["asset_id"] = "Bearing1_4"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(
        XjtuCharacterizationArtifactError,
        match="lifecycle runs do not match",
    ):
        load_xjtu_characterization_artifacts(feature_table_path, summary_path)


def test_loads_undefined_correlations_for_constant_features(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    feature_table_path = tmp_path / "features.csv"
    _write_summary(summary_path)
    _write_feature_table(feature_table_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["correlations"]["global"][0]["pearson"] = None
    summary["correlations"]["by_condition"]["35Hz12kN"][0]["spearman"] = None
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    data = load_xjtu_characterization_artifacts(feature_table_path, summary_path)

    assert data.correlations_for(None)[0].pearson is None
    assert data.correlations_for("35Hz12kN")[0].spearman is None


def test_rejects_duplicate_correlation_pairs(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    feature_table_path = tmp_path / "features.csv"
    _write_summary(summary_path)
    _write_feature_table(feature_table_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["correlations"]["global"].append(summary["correlations"]["global"][0])
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(
        XjtuCharacterizationArtifactError,
        match="correlation pairs differ",
    ):
        load_xjtu_characterization_artifacts(feature_table_path, summary_path)


def test_rejects_lifecycle_segment_count_mismatch(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    feature_table_path = tmp_path / "features.csv"
    _write_summary(summary_path)
    _write_feature_table(feature_table_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["lifecycle_segments"]["runs"][0]["segments"]["early_third"]["acquisition_count"] = 2
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(
        XjtuCharacterizationArtifactError,
        match="segment counts do not match",
    ):
        load_xjtu_characterization_artifacts(feature_table_path, summary_path)
