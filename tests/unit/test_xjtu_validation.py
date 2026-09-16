from pathlib import Path

import pytest

from industrial_phm.adapters import validate_xjtu_source
from industrial_phm.cli import main

_VALID_HEADER = "Horizontal_vibration_signals,Vertical_vibration_signals\n"
_VALID_ROW = "0.0,0.0\n"


def _write_valid_acquisition(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_VALID_HEADER + (_VALID_ROW * 32_768), encoding="utf-8")


def test_xjtu_validation_samples_representative_acquisitions_by_default(tmp_path: Path) -> None:
    bearing = tmp_path / "40Hz10kN" / "Bearing3_2"
    for index in range(1, 5):
        _write_valid_acquisition(bearing / f"{index}.csv")

    report = validate_xjtu_source(tmp_path)

    assert report.operating_condition_count == 1
    assert report.bearing_run_count == 1
    assert report.acquisition_count == 4
    assert report.checked_acquisition_count == 3
    assert report.channels == (
        "Horizontal_vibration_signals",
        "Vertical_vibration_signals",
    )
    assert report.samples_per_acquisition == 32_768
    assert report.sampling_rate_hz == 25_600.0
    assert not report.profile_matches
    assert (
        "acquisition count mismatch: 40Hz10kN/Bearing3_2: expected 2496, found 4"
        in report.profile_issues
    )


def test_xjtu_validation_full_mode_checks_every_observed_acquisition(tmp_path: Path) -> None:
    bearing = tmp_path / "40Hz10kN" / "Bearing3_5"
    for index in range(1, 3):
        _write_valid_acquisition(bearing / f"{index}.csv")

    report = validate_xjtu_source(tmp_path, full=True)

    assert report.full
    assert report.acquisition_count == 2
    assert report.checked_acquisition_count == 2


def test_cli_data_validate_reports_incomplete_xjtu_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_valid_acquisition(tmp_path / "35Hz12kN" / "Bearing1_1" / "1.csv")

    assert main(["data", "validate", "xjtu-sy", "--source", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "waveform compatibility: PASS (sampled)" in captured.out
    assert "profile compatibility: FAIL" in captured.out
    assert "acquisitions: 1" in captured.out
    assert "profile issue:" in captured.err


def test_cli_data_validate_rejects_dataset_without_validator(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["data", "validate", "ai4i-2020", "--source", str(tmp_path)]) == 2

    captured = capsys.readouterr()
    assert "dataset-specific validation is not implemented for ai4i-2020" in captured.err
