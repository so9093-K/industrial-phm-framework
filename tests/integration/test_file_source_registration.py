from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    FileSourceDiscoveryError,
    FileSourceMode,
    InMemorySourceRepository,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    RegisteredSource,
    discover_file_source,
    load_registered_file_source_observation,
    receive_registered_file_source_observation,
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
    assert discovery.preview_rows == (("2026-09-23T10:00:00+09:00", "-1.0", "42.0"),)


def test_discover_history_reports_only_columns_common_to_every_file(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    (history / "a.csv").write_text(
        "timestamp,vibration_x,temperature,optional_a\n2026-09-23T10:00:00+09:00,-1.0,42.0,a\n",
        encoding="utf-8",
    )
    (history / "b.csv").write_text(
        "temperature,timestamp,vibration_x,optional_b\n42.2,2026-09-23T11:00:00+09:00,1.0,b\n",
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


def test_load_registered_snapshot_projects_current_observation(tmp_path: Path) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )
    source = _registered_source(source_path)

    loaded = load_registered_file_source_observation(source)

    assert loaded.timeline is None
    assert loaded.segment_count == 1
    assert loaded.latest.source_id == source.source_id
    assert loaded.latest.asset_id == source.asset_id
    assert loaded.latest.measurement_point_id == source.measurement_point_id
    assert loaded.latest.source_snapshot is not None
    assert loaded.latest.source_snapshot.name == "pump.csv"


def test_receive_registered_snapshot_records_platform_receipt_and_lag(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )

    received = receive_registered_file_source_observation(
        _registered_source(source_path),
        received_at=datetime.fromisoformat("2026-09-23T10:00:06+09:00"),
    )

    assert received.observation.latest.observed_end_at == datetime.fromisoformat(
        "2026-09-23T10:00:01+09:00"
    )
    assert received.receipt.received_at == datetime.fromisoformat("2026-09-23T10:00:06+09:00")
    assert received.receipt.lag_seconds == 5.0


def test_received_registered_snapshot_can_restore_latest_receipt_after_reopen(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )
    runtime_path = tmp_path / "runtime" / "source-runtime.json"
    received = receive_registered_file_source_observation(
        _registered_source(source_path),
        received_at=datetime.fromisoformat("2026-09-23T10:00:06+09:00"),
    )

    JsonSourceRuntimeRepository(runtime_path).record_receipt(received.receipt)

    reopened = JsonSourceRuntimeRepository(runtime_path)
    assert reopened.get_latest_receipt(received.receipt.source_id) == received.receipt


def test_receive_registered_snapshot_keeps_lag_unavailable_for_naive_source_time(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00,-1.0,42.0\n"
        "2026-09-23T10:00:01,1.0,42.2\n",
        encoding="utf-8",
    )

    received = receive_registered_file_source_observation(
        _registered_source(source_path),
        received_at=datetime.fromisoformat("2026-09-23T10:00:06+09:00"),
    )

    assert received.receipt.lag_seconds is None
    assert received.receipt.lag_unavailable_reason == "source observation timezone is unavailable"


def test_load_registered_history_preserves_timeline_and_latest_segment(
    tmp_path: Path,
) -> None:
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

    loaded = load_registered_file_source_observation(
        _registered_source(history, mode=FileSourceMode.HISTORY_DIRECTORY)
    )

    assert loaded.timeline is not None
    assert loaded.segment_count == 2
    assert loaded.timeline.latest == loaded.latest
    assert loaded.latest.source_snapshot is not None
    assert loaded.latest.source_snapshot.name == "late.csv"


def test_load_registered_source_revalidates_changed_bytes_after_registration(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )
    source = _registered_source(source_path)
    repository = InMemorySourceRepository()
    register_file_source(source, repository)

    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,not-numeric,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be numeric"):
        load_registered_file_source_observation(repository.get(source.source_id))


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
    assert validation.observed_start_at == datetime.fromisoformat("2026-09-23T10:00:00+09:00")
    assert validation.observed_end_at == datetime.fromisoformat("2026-09-23T11:00:01+09:00")


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


def test_register_file_source_persists_to_json_repository(tmp_path: Path) -> None:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x,temperature\n"
        "2026-09-23T10:00:00+09:00,-1.0,42.0\n"
        "2026-09-23T10:00:01+09:00,1.0,42.2\n",
        encoding="utf-8",
    )
    source = _registered_source(source_path)
    registry_path = tmp_path / "state" / "sources.json"

    validation = register_file_source(source, JsonSourceRepository(registry_path))

    assert validation.total_sample_count == 2
    assert JsonSourceRepository(registry_path).get(source.source_id) == source
