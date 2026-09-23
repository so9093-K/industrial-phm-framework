from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    FileSourceDiscoveryError,
    FileSourceMode,
    InMemorySourceRepository,
    RegisteredSource,
    discover_file_source,
    register_file_source,
    validate_registered_file_source,
)
from industrial_phm.contracts import DataQualityState


def _registered_source(
    source_path: Path,
    *,
    mode: FileSourceMode = FileSourceMode.SNAPSHOT,
    sampling_rate_hz: float | None = None,
    tolerance: float | None = None,
) -> RegisteredSource:
    return RegisteredSource(
        source_id="field:pump-01",
        name="Pump 01 field source",
        config=FileSourceConfig(
            source_path=str(source_path),
            asset_id="pump-01",
            measurement_point_id="drive-end-bearing",
            channel_columns=("vibration_x", "temperature"),
            mode=mode,
            timestamp_column="timestamp",
            sampling_rate_hz=sampling_rate_hz,
            sampling_rate_tolerance_ratio=tolerance,
            minimum_sample_count=2,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )


def test_discover_snapshot_reports_columns_size_and_preview(tmp_path: Path) -> None:
    source = tmp_path / "pump.csv"
    source.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )

    discovery = discover_file_source(source, FileSourceMode.SNAPSHOT, preview_row_limit=1)

    assert discovery.file_count == 1
    assert discovery.total_size_bytes == source.stat().st_size
    assert discovery.common_columns == ("timestamp", "vibration_x", "temperature")
    assert discovery.representative_columns == discovery.common_columns
    assert discovery.header_variant_count == 1
    assert discovery.representative_file == "pump.csv"
    assert discovery.preview_rows == (
        ("2026-09-23T10:00:00+09:00", "-1.0", "42.0"),
    )


def test_discover_history_reports_only_columns_common_to_every_file(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    (history / "a.csv").write_text(
        "timestamp,vibration_x,temperature,optional_a\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0,a\n",
        encoding="utf-8",
    )
    (history / "b.csv").write_text(
        "temperature,timestamp,vibration_x,optional_b\n"
        "42.2,2026-09-23T11:00:00+09:00,1.0,b\n",
        encoding="utf-8",
    )

    discovery = discover_file_source(history, FileSourceMode.HISTORY_DIRECTORY)

    assert discovery.file_count == 2
    assert discovery.common_columns == ("timestamp", "vibration_x", "temperature")
    assert discovery.header_variant_count == 2
    assert discovery.representative_file == "a.csv"


def test_discover_history_rejects_directory_without_csv_files(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    (history / "notes.txt").write_text("not csv", encoding="utf-8")

    with pytest.raises(FileSourceDiscoveryError, match="contains no CSV files"):
        discover_file_source(history, FileSourceMode.HISTORY_DIRECTORY)


def test_discover_rejects_duplicate_header_columns(tmp_path: Path) -> None:
    source = tmp_path / "pump.csv"
    source.write_text("timestamp,value,value\n2026-09-23T10:00:00+09:00,1,2\n", encoding="utf-8")

    with pytest.raises(FileSourceDiscoveryError, match="duplicate column"):
        discover_file_source(source, FileSourceMode.SNAPSHOT)


def test_validate_snapshot_reuses_existing_quality_semantics(tmp_path: Path) -> None:
    source = tmp_path / "pump.csv"
    source.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )

    validation = validate_registered_file_source(
        _registered_source(source, sampling_rate_hz=2.0, tolerance=0.05)
    )

    assert validation.segment_count == 1
    assert validation.total_sample_count == 2
    assert validation.quality_state == DataQualityState.WARNING
    assert validation.quality_issue_codes == ("sampling-rate-mismatch",)
    assert validation.source_snapshots[0].name == "pump.csv"


def test_validate_history_reuses_timeline_order_and_non_overlap_rules(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    (history / "late.csv").write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T11:00:00+09:00,-2.0,43.0\n"
        "2026-09-23T11:00:01+09:00,2.0,43.2\n",
        encoding="utf-8",
    )
    (history / "early.csv").write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )

    validation = validate_registered_file_source(
        _registered_source(history, mode=FileSourceMode.HISTORY_DIRECTORY)
    )

    assert validation.segment_count == 2
    assert validation.total_sample_count == 4
    assert validation.quality_state == DataQualityState.PASS
    assert validation.observed_start_at == datetime.fromisoformat(
        "2026-09-23T10:00:00+09:00"
    )
    assert validation.observed_end_at == datetime.fromisoformat(
        "2026-09-23T11:00:01+09:00"
    )


def test_register_file_source_validates_before_persistence(tmp_path: Path) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )
    source = _registered_source(source_path)
    repository = InMemorySourceRepository()

    validation = register_file_source(source, repository)

    assert validation.quality_state == DataQualityState.PASS
    assert repository.get(source.source_id) == source


def test_register_file_source_does_not_persist_invalid_source(tmp_path: Path) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,not-numeric,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )
    source = _registered_source(source_path)
    repository = InMemorySourceRepository()

    with pytest.raises(ValueError, match="must be numeric"):
        register_file_source(source, repository)

    assert repository.list_sources() == ()
