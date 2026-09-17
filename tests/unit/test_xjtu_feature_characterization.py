import csv
import json
from pathlib import Path

import pytest

from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.experiments.xjtu_characterization import (
    XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
    XjtuFeatureCharacterizationError,
    write_xjtu_characterization_artifacts,
)
from industrial_phm.experiments.xjtu_feature_analysis import (
    XjtuFeatureAnalysisError,
    load_xjtu_feature_analysis,
)
from industrial_phm.features import VibrationFeatureVector, extract_vibration_features

_FOLD_1_TRAIN = (
    "Bearing1_3",
    "Bearing1_4",
    "Bearing1_5",
    "Bearing2_3",
    "Bearing2_4",
    "Bearing2_5",
    "Bearing3_3",
    "Bearing3_4",
    "Bearing3_5",
)


def _condition_for(asset_id: str) -> str:
    if asset_id.startswith("Bearing1_"):
        return "35Hz12kN"
    if asset_id.startswith("Bearing2_"):
        return "37.5Hz11kN"
    if asset_id.startswith("Bearing3_"):
        return "40Hz10kN"
    raise AssertionError(f"unexpected synthetic asset: {asset_id}")


def _vector(
    *,
    asset_id: str,
    acquisition_index: int,
    scale: float,
) -> VibrationFeatureVector:
    series = CanonicalTimeSeries(
        asset_id=asset_id,
        timestamps=None,
        channels=(
            "Horizontal_vibration_signals",
            "Vertical_vibration_signals",
        ),
        values=[
            (-1.0 * scale, -2.0 * scale),
            (0.0, -1.0 * scale),
            (1.0 * scale, 1.0 * scale),
            (0.0, 2.0 * scale),
        ],
        sampling_rate_hz=25_600.0,
        metadata={
            "dataset_id": "xjtu-sy",
            "operating_condition": _condition_for(asset_id),
            "acquisition_index": acquisition_index,
        },
    )
    return extract_vibration_features(series)


def _fold_1_train_vectors() -> list[VibrationFeatureVector]:
    vectors: list[VibrationFeatureVector] = []
    for asset_factor, asset_id in enumerate(_FOLD_1_TRAIN, start=1):
        for acquisition_index in (1, 2, 3):
            vectors.append(
                _vector(
                    asset_id=asset_id,
                    acquisition_index=acquisition_index,
                    scale=float(asset_factor * acquisition_index),
                )
            )
    return vectors


def test_characterization_writes_development_evidence_without_test_data(
    tmp_path: Path,
) -> None:
    artifacts = write_xjtu_characterization_artifacts(
        _fold_1_train_vectors(),
        tmp_path,
        fold_id="fold-1",
        partition="train",
    )

    assert artifacts.acquisition_count == 27
    assert artifacts.bearing_run_count == 9
    assert artifacts.operating_condition_count == 3
    assert artifacts.fold_id == "fold-1"
    assert artifacts.partition == "train"

    with artifacts.feature_table_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 27
    assert {row["asset_id"] for row in rows} == set(_FOLD_1_TRAIN)

    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    assert summary["schema_id"] == XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID
    assert summary["acquisition_count"] == 27
    assert summary["bearing_run_count"] == 9
    assert summary["experiment_scope"]["fold_id"] == "fold-1"
    assert summary["experiment_scope"]["partition"] == "train"
    assert summary["experiment_scope"]["test_partition_included"] is False
    assert summary["run_length_imbalance"]["min_acquisitions"] == 3
    assert summary["run_length_imbalance"]["max_acquisitions"] == 3

    rms_name = "feature.Horizontal_vibration_signals.rms"
    std_name = "feature.Horizontal_vibration_signals.standard_deviation"
    correlation = next(
        entry
        for entry in summary["correlations"]["global"]
        if entry["left"] == rms_name and entry["right"] == std_name
    )
    assert correlation["pearson"] == pytest.approx(1.0)
    assert correlation["spearman"] == pytest.approx(1.0)

    first_run = summary["lifecycle_segments"]["runs"][0]
    assert first_run["segments"]["early_third"]["acquisition_count"] == 1
    assert first_run["segments"]["middle_third"]["acquisition_count"] == 1
    assert first_run["segments"]["late_third"]["acquisition_count"] == 1

    assert summary["decision_boundary"]["feature_selection"] == "undecided"
    assert summary["decision_boundary"]["normal_reference"] == "undecided"


def test_feature_analysis_loads_generated_development_artifacts(tmp_path: Path) -> None:
    artifacts = write_xjtu_characterization_artifacts(
        _fold_1_train_vectors(),
        tmp_path,
        fold_id="fold-1",
        partition="train",
    )

    analysis = load_xjtu_feature_analysis(
        artifacts.feature_table_path,
        artifacts.summary_path,
    )

    assert analysis.feature_set_id == "vibration-statistical-v1"
    assert analysis.fold_id == "fold-1"
    assert analysis.partition == "train"
    assert analysis.bearing_run_count == 9
    assert analysis.operating_condition_count == 3
    assert analysis.operating_conditions == ("35Hz12kN", "37.5Hz11kN", "40Hz10kN")
    assert analysis.asset_ids == tuple(sorted(_FOLD_1_TRAIN))
    assert len(analysis.records) == 27

    rms_name = "feature.Horizontal_vibration_signals.rms"
    series = analysis.feature_series(rms_name, asset_ids=("Bearing1_3",))
    assert [point.acquisition_index for point in series] == [1, 2, 3]
    assert [point.retrospective_lifecycle_fraction for point in series] == pytest.approx(
        [1 / 3, 2 / 3, 1.0]
    )
    assert [point.value for point in series] == sorted(point.value for point in series)


def test_feature_analysis_filters_by_operating_condition(tmp_path: Path) -> None:
    artifacts = write_xjtu_characterization_artifacts(
        _fold_1_train_vectors(),
        tmp_path,
        fold_id="fold-1",
        partition="train",
    )
    analysis = load_xjtu_feature_analysis(
        artifacts.feature_table_path,
        artifacts.summary_path,
    )

    rms_name = "feature.Vertical_vibration_signals.rms"
    series = analysis.feature_series(rms_name, operating_condition="37.5Hz11kN")

    assert {point.asset_id for point in series} == {"Bearing2_3", "Bearing2_4", "Bearing2_5"}
    assert {point.operating_condition for point in series} == {"37.5Hz11kN"}


def test_feature_analysis_rejects_unknown_feature_or_asset(tmp_path: Path) -> None:
    artifacts = write_xjtu_characterization_artifacts(
        _fold_1_train_vectors(),
        tmp_path,
        fold_id="fold-1",
        partition="train",
    )
    analysis = load_xjtu_feature_analysis(
        artifacts.feature_table_path,
        artifacts.summary_path,
    )

    with pytest.raises(XjtuFeatureAnalysisError, match="unknown feature"):
        analysis.feature_series("feature.missing")
    with pytest.raises(XjtuFeatureAnalysisError, match="unknown XJTU asset"):
        analysis.feature_series(
            "feature.Horizontal_vibration_signals.rms",
            asset_ids=("Bearing9_9",),
        )


def test_feature_analysis_rejects_test_scope_in_summary(tmp_path: Path) -> None:
    artifacts = write_xjtu_characterization_artifacts(
        _fold_1_train_vectors(),
        tmp_path,
        fold_id="fold-1",
        partition="train",
    )
    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    summary["experiment_scope"]["partition"] = "test"
    artifacts.summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(XjtuFeatureAnalysisError, match="train or validation"):
        load_xjtu_feature_analysis(
            artifacts.feature_table_path,
            artifacts.summary_path,
        )


def test_characterization_rejects_non_contiguous_lifecycle_records(tmp_path: Path) -> None:
    vectors = [
        _vector(asset_id="Bearing1_3", acquisition_index=1, scale=1.0),
        _vector(asset_id="Bearing1_3", acquisition_index=3, scale=3.0),
    ]
    vectors.extend(
        _vector(asset_id=asset_id, acquisition_index=1, scale=float(index))
        for index, asset_id in enumerate(_FOLD_1_TRAIN[1:], start=2)
    )

    with pytest.raises(XjtuFeatureCharacterizationError, match=r"contiguous 1\.\.N"):
        write_xjtu_characterization_artifacts(
            vectors,
            tmp_path,
            fold_id="fold-1",
            partition="train",
        )


def test_characterization_does_not_allow_test_partition(tmp_path: Path) -> None:
    with pytest.raises(XjtuFeatureCharacterizationError, match="test is reserved"):
        write_xjtu_characterization_artifacts(
            _fold_1_train_vectors(),
            tmp_path,
            fold_id="fold-1",
            partition="test",  # type: ignore[arg-type]
        )
