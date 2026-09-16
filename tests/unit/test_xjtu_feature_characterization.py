import csv
import json
from pathlib import Path

import pytest

from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.experiments import (
    XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
    XjtuFeatureCharacterizationError,
    write_xjtu_characterization_artifacts,
)
from industrial_phm.features import extract_vibration_features


def _vector(
    *,
    asset_id: str,
    operating_condition: str,
    acquisition_index: int,
    scale: float,
):
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
            "operating_condition": operating_condition,
            "acquisition_index": acquisition_index,
        },
    )
    return extract_vibration_features(series)


def test_characterization_writes_evidence_without_making_experiment_decisions(
    tmp_path: Path,
) -> None:
    vectors = [
        _vector(
            asset_id="Bearing1_1",
            operating_condition="35Hz12kN",
            acquisition_index=index,
            scale=float(index),
        )
        for index in (1, 2, 3)
    ] + [
        _vector(
            asset_id="Bearing2_1",
            operating_condition="37.5Hz11kN",
            acquisition_index=index,
            scale=float(index * 2),
        )
        for index in (1, 2, 3)
    ]

    artifacts = write_xjtu_characterization_artifacts(vectors, tmp_path)

    assert artifacts.acquisition_count == 6
    assert artifacts.bearing_run_count == 2
    assert artifacts.operating_condition_count == 2

    with artifacts.feature_table_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 6
    assert rows[0]["asset_id"] == "Bearing1_1"
    assert rows[0]["meta.acquisition_index"] == "1"

    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    assert summary["schema_id"] == XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID
    assert summary["acquisition_count"] == 6
    assert summary["bearing_run_count"] == 2
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


def test_characterization_rejects_non_contiguous_lifecycle_records(tmp_path: Path) -> None:
    vectors = [
        _vector(
            asset_id="Bearing1_1",
            operating_condition="35Hz12kN",
            acquisition_index=index,
            scale=float(index),
        )
        for index in (1, 3)
    ]

    with pytest.raises(XjtuFeatureCharacterizationError, match=r"contiguous 1\.\.N"):
        write_xjtu_characterization_artifacts(vectors, tmp_path)
