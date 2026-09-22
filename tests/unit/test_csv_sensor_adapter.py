import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.adapters import (
    CsvSensorAdapter,
    CsvSensorLayout,
    CsvSensorSourceError,
    DomainAdapter,
    validate_csv_sensor_source,
)
from industrial_phm.contracts import DataQualitySeverity


def _write_csv(tmp_path: Path, content: str) -> Path:
    source = tmp_path / "sensor.csv"
    source.write_text(content, encoding="utf-8")
    return source


def test_rate_based_csv_adapter_preserves_source_byte_identity(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path,
        "vibration,temperature\n1.0,20.0\n2.0,20.5\n3.0,21.0\n",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        channel_columns=("vibration", "temperature"),
        sampling_rate_hz=100.0,
        metadata={"site": "pilot"},
    )

    report = validate_csv_sensor_source(source, layout)
    adapter = CsvSensorAdapter(layout)
    series = tuple(adapter.iter_series(source))

    assert isinstance(adapter, DomainAdapter)
    assert adapter.domain == "field-csv"
    assert report.sample_count == 3
    assert report.quality_issues == ()
    assert report.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(series) == 1
    assert series[0].asset_id == "pump-01"
    assert series[0].timestamps is None
    assert series[0].sampling_rate_hz == 100.0
    assert series[0].channels == ("vibration", "temperature")
    assert series[0].values == ((1.0, 20.0), (2.0, 20.5), (3.0, 21.0))
    assert series[0].metadata["site"] == "pilot"
    assert series[0].metadata["source_adapter"] == "field-csv-v1"
    assert series[0].metadata["source_sha256"] == report.source_sha256


def test_timestamp_csv_reports_irregular_sampling_without_regridding(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path,
        "timestamp,vibration\n"
        "2026-09-22T10:00:00+09:00,1.0\n"
        "2026-09-22T10:00:01+09:00,2.0\n"
        "2026-09-22T10:00:03+09:00,3.0\n",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        timestamp_column="timestamp",
        channel_columns=("vibration",),
    )

    report = validate_csv_sensor_source(source, layout)
    series = next(iter(CsvSensorAdapter(layout).iter_series(source)))

    assert report.minimum_interval_seconds == 1.0
    assert report.maximum_interval_seconds == 2.0
    assert len(report.quality_issues) == 1
    assert report.quality_issues[0].code == "irregular-sampling"
    assert report.quality_issues[0].severity == DataQualitySeverity.WARNING
    assert series.sampling_rate_hz is None
    assert series.timestamps == (
        datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
        datetime.fromisoformat("2026-09-22T10:00:01+09:00"),
        datetime.fromisoformat("2026-09-22T10:00:03+09:00"),
    )


def test_csv_adapter_rejects_missing_required_channel(tmp_path: Path) -> None:
    source = _write_csv(tmp_path, "vibration\n1.0\n")
    layout = CsvSensorLayout(
        asset_id="pump-01",
        channel_columns=("vibration", "temperature"),
        sampling_rate_hz=100.0,
    )

    with pytest.raises(CsvSensorSourceError, match="missing required columns"):
        validate_csv_sensor_source(source, layout)


@pytest.mark.parametrize("value", ["", "nan", "inf", "not-a-number"])
def test_csv_adapter_rejects_missing_nonfinite_or_nonnumeric_values(
    tmp_path: Path,
    value: str,
) -> None:
    source = _write_csv(tmp_path, f"vibration\n{value}\n")
    layout = CsvSensorLayout(
        asset_id="pump-01",
        channel_columns=("vibration",),
        sampling_rate_hz=100.0,
    )

    with pytest.raises(CsvSensorSourceError):
        validate_csv_sensor_source(source, layout)


def test_csv_adapter_rejects_non_increasing_timestamps(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path,
        "timestamp,vibration\n2026-09-22T10:00:01+09:00,1.0\n2026-09-22T10:00:01+09:00,2.0\n",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        timestamp_column="timestamp",
        channel_columns=("vibration",),
    )

    with pytest.raises(CsvSensorSourceError, match="strictly increasing"):
        validate_csv_sensor_source(source, layout)


def test_csv_adapter_rejects_mixed_timestamp_awareness(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path,
        "timestamp,vibration\n2026-09-22T10:00:00,1.0\n2026-09-22T10:00:01+09:00,2.0\n",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        timestamp_column="timestamp",
        channel_columns=("vibration",),
    )

    with pytest.raises(CsvSensorSourceError, match="timezone awareness"):
        validate_csv_sensor_source(source, layout)


def test_csv_adapter_enforces_declared_minimum_sample_count(tmp_path: Path) -> None:
    source = _write_csv(tmp_path, "vibration\n1.0\n2.0\n")
    layout = CsvSensorLayout(
        asset_id="pump-01",
        channel_columns=("vibration",),
        sampling_rate_hz=100.0,
        minimum_sample_count=3,
    )

    with pytest.raises(CsvSensorSourceError, match="minimum_sample_count"):
        validate_csv_sensor_source(source, layout)


def test_csv_layout_requires_an_explicit_time_basis() -> None:
    with pytest.raises(ValueError, match="timestamp_column or sampling_rate_hz"):
        CsvSensorLayout(
            asset_id="pump-01",
            channel_columns=("vibration",),
        )


def test_csv_layout_rejects_timestamp_as_sensor_channel() -> None:
    with pytest.raises(ValueError, match="must not also be a channel"):
        CsvSensorLayout(
            asset_id="pump-01",
            timestamp_column="timestamp",
            channel_columns=("timestamp",),
        )


def test_timestamp_rate_consistency_reports_declared_rate_mismatch(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path,
        "timestamp,vibration\n"
        "2026-09-22T10:00:00+09:00,1.0\n"
        "2026-09-22T10:00:01+09:00,2.0\n"
        "2026-09-22T10:00:02+09:00,3.0\n",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        timestamp_column="timestamp",
        channel_columns=("vibration",),
        sampling_rate_hz=2.0,
        sampling_rate_tolerance_ratio=0.05,
    )

    report = validate_csv_sensor_source(source, layout)

    assert report.maximum_sampling_interval_deviation_ratio == pytest.approx(1.0)
    assert [issue.code for issue in report.quality_issues] == ["sampling-rate-mismatch"]


def test_timestamp_rate_consistency_respects_explicit_tolerance(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path,
        "timestamp,vibration\n"
        "2026-09-22T10:00:00+09:00,1.0\n"
        "2026-09-22T10:00:01+09:00,2.0\n"
        "2026-09-22T10:00:02+09:00,3.0\n",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        timestamp_column="timestamp",
        channel_columns=("vibration",),
        sampling_rate_hz=1.0,
        sampling_rate_tolerance_ratio=0.0,
    )

    report = validate_csv_sensor_source(source, layout)

    assert report.maximum_sampling_interval_deviation_ratio == 0.0
    assert report.quality_issues == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sampling_rate_tolerance_ratio": 0.1},
        {
            "timestamp_column": "timestamp",
            "sampling_rate_tolerance_ratio": 0.1,
        },
    ],
)
def test_csv_layout_requires_both_time_sources_for_rate_tolerance(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="requires timestamp_column and sampling_rate_hz"):
        CsvSensorLayout(
            asset_id="pump-01",
            channel_columns=("vibration",),
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("tolerance", [-0.1, float("inf"), float("nan")])
def test_csv_layout_rejects_invalid_sampling_rate_tolerance(tolerance: float) -> None:
    with pytest.raises(ValueError, match="finite non-negative"):
        CsvSensorLayout(
            asset_id="pump-01",
            timestamp_column="timestamp",
            channel_columns=("vibration",),
            sampling_rate_hz=1.0,
            sampling_rate_tolerance_ratio=tolerance,
        )

