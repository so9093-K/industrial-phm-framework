from pathlib import Path

import pytest

from industrial_phm.adapters import (
    ImsBearingAdapter,
    ImsBearingSourceError,
    validate_ims_source,
)
from industrial_phm.cli import main

_SAMPLE_COUNT = 20_480


def _write_acquisition(path: Path, values: tuple[float, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = "\t".join(str(value) for value in values) + "\n"
    path.write_text(row * _SAMPLE_COUNT, encoding="ascii")


def _write_minimal_source(root: Path) -> None:
    _write_acquisition(
        root / "1st_test" / "2003.10.22.12.06.24",
        (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0),
    )
    _write_acquisition(
        root / "2nd_test" / "2004.02.12.10.32.39",
        (11.0, 12.0, 13.0, 14.0),
    )
    _write_acquisition(
        root / "4th_test" / "txt" / "2004.04.04.19.11.57",
        (21.0, 22.0, 23.0, 24.0),
    )


def test_ims_adapter_splits_multibearing_acquisitions_and_preserves_time(tmp_path: Path) -> None:
    _write_minimal_source(tmp_path)

    adapter = ImsBearingAdapter()
    series = list(adapter.iter_series(tmp_path))

    assert adapter.domain == "ims-bearings"
    assert len(series) == 12

    set_1_bearing_1 = series[0]
    assert set_1_bearing_1.asset_id == "set-1-bearing-1"
    assert set_1_bearing_1.channels == ("x_axis_vibration", "y_axis_vibration")
    assert set_1_bearing_1.values[0] == (1.0, 2.0)
    assert len(set_1_bearing_1.values) == _SAMPLE_COUNT
    assert set_1_bearing_1.sampling_rate_hz == 20_000.0
    assert set_1_bearing_1.metadata["acquisition_timestamp"] == "2003-10-22T12:06:24"
    assert set_1_bearing_1.metadata["acquisition_time_basis"] == "filename-local-clock"
    assert set_1_bearing_1.metadata["archive_scope"] == "readme-documented"
    assert set_1_bearing_1.metadata["source_archive_member"] == "1st_test.rar"
    assert set_1_bearing_1.metadata["source_file"] == "1st_test/2003.10.22.12.06.24"

    set_2_bearing_4 = series[7]
    assert set_2_bearing_4.asset_id == "set-2-bearing-4"
    assert set_2_bearing_4.channels == ("vibration",)
    assert set_2_bearing_4.values[0] == (14.0,)

    set_3_bearing_1 = series[8]
    assert set_3_bearing_1.metadata["test_id"] == "set-3"
    assert set_3_bearing_1.metadata["archive_scope"] == "archive-extension"
    assert set_3_bearing_1.metadata["source_file"] == "4th_test/txt/2004.04.04.19.11.57"


def test_ims_validation_samples_each_observed_test_and_reports_profile_gaps(
    tmp_path: Path,
) -> None:
    _write_minimal_source(tmp_path)

    report = validate_ims_source(tmp_path)

    assert len(report.tests) == 3
    assert report.acquisition_count == 3
    assert report.checked_acquisition_count == 3
    assert report.samples_per_acquisition == _SAMPLE_COUNT
    assert report.sampling_rate_hz == 20_000.0
    assert not report.profile_matches
    assert "acquisition count mismatch: set-1: expected 2156, found 1" in report.profile_issues


def test_ims_validation_full_mode_checks_every_observed_acquisition(tmp_path: Path) -> None:
    directory = tmp_path / "2nd_test"
    for minute in (32, 42, 52, 2):
        hour = 10 if minute != 2 else 11
        _write_acquisition(
            directory / f"2004.02.12.{hour:02d}.{minute:02d}.39",
            (11.0, 12.0, 13.0, 14.0),
        )

    report = validate_ims_source(tmp_path, full=True)

    assert report.full
    assert report.acquisition_count == 4
    assert report.checked_acquisition_count == 4


def test_cli_data_validate_reports_incomplete_ims_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_minimal_source(tmp_path)

    assert main(["data", "validate", "ims-bearings", "--source", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "dataset: ims-bearings" in captured.out
    assert "waveform compatibility: PASS (sampled)" in captured.out
    assert "profile compatibility: FAIL" in captured.out
    assert "profile issue:" in captured.err


def test_ims_adapter_rejects_unexpected_waveform_width(tmp_path: Path) -> None:
    path = tmp_path / "2nd_test" / "2004.02.12.10.32.39"
    _write_acquisition(path, (1.0, 2.0, 3.0))

    with pytest.raises(ImsBearingSourceError, match="unexpected IMS waveform width"):
        next(iter(ImsBearingAdapter().iter_series(tmp_path)))


def test_ims_adapter_rejects_non_timestamp_filename(tmp_path: Path) -> None:
    path = tmp_path / "1st_test" / "not-a-timestamp"
    _write_acquisition(path, (1.0,) * 8)

    with pytest.raises(ImsBearingSourceError, match="acquisition filename must match"):
        next(iter(ImsBearingAdapter().iter_series(tmp_path)))
