from pathlib import Path

import pytest

from industrial_phm.adapters import DomainAdapter, XjtuSyAdapter, XjtuSySourceError


_VALID_HEADER = "Horizontal_vibration_signals,Vertical_vibration_signals\n"
_VALID_ROW = "0.0,0.0\n"


def _bearing_dir(root: Path) -> Path:
    bearing = root / "40Hz10kN" / "Bearing3_2"
    bearing.mkdir(parents=True)
    return bearing


def _write_valid_acquisition(path: Path) -> None:
    path.write_text(_VALID_HEADER + (_VALID_ROW * 32_768), encoding="utf-8")


def test_xjtu_adapter_reads_acquisitions_lazily_in_numeric_order(tmp_path: Path) -> None:
    bearing = _bearing_dir(tmp_path)
    _write_valid_acquisition(bearing / "1.csv")
    _write_valid_acquisition(bearing / "2.csv")
    for index in range(3, 11):
        (bearing / f"{index}.csv").touch()

    adapter = XjtuSyAdapter()
    assert isinstance(adapter, DomainAdapter)
    assert adapter.domain == "xjtu-sy"

    series = iter(adapter.iter_series(tmp_path))
    first = next(series)
    second = next(series)

    assert first.asset_id == "Bearing3_2"
    assert first.timestamps is None
    assert first.channels == (
        "Horizontal_vibration_signals",
        "Vertical_vibration_signals",
    )
    assert len(first.values) == 32_768
    assert first.sampling_rate_hz == 25_600.0
    assert first.labels is None
    assert first.rul is None
    assert first.metadata["operating_condition"] == "40Hz10kN"
    assert first.metadata["rotational_speed_hz"] == 40.0
    assert first.metadata["radial_load_kn"] == 10.0
    assert first.metadata["acquisition_index"] == 1
    assert first.metadata["acquisition_period_seconds"] == 60.0
    assert first.metadata["source_file"] == "40Hz10kN/Bearing3_2/1.csv"
    assert second.metadata["acquisition_index"] == 2


def test_xjtu_adapter_rejects_non_contiguous_acquisition_sequence(tmp_path: Path) -> None:
    bearing = _bearing_dir(tmp_path)
    (bearing / "1.csv").touch()
    (bearing / "3.csv").touch()

    with pytest.raises(XjtuSySourceError, match="contiguous 1..N"):
        next(iter(XjtuSyAdapter().iter_series(tmp_path)))


def test_xjtu_adapter_rejects_unexpected_csv_header(tmp_path: Path) -> None:
    bearing = _bearing_dir(tmp_path)
    (bearing / "1.csv").write_text("horizontal,vertical\n0.0,0.0\n", encoding="utf-8")

    with pytest.raises(XjtuSySourceError, match="unexpected XJTU-SY CSV header"):
        next(iter(XjtuSyAdapter().iter_series(tmp_path)))
