import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest

from industrial_phm.adapters.aihub_power import iter_power_observations
from industrial_phm.adapters.aihub_power_history import (
    PowerHistoryBinding,
    project_power_observation,
)
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.presentation.measurement_history import (
    latest_measurement_rows,
    measurement_aggregation_summary,
    measurement_history_rows,
)


def _load_tool(name):
    path = Path(__file__).resolve().parents[2] / "tools" / "aihub" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"aihub_{name}_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import_history = _load_tool("history").import_history
profile_archive = _load_tool("profile").profile_archive

pytest.importorskip("ijson")
pytest.importorskip("duckdb")

LOCAL = datetime(2021, 2, 3, 7, 1, 7)
UTC_START = datetime(2021, 2, 2, 22, 1, 7, tzinfo=UTC)
MEMBER = "보일러/SourceData_391.json"


def _archive(tmp_path, values=(1.0, None, 2.0)):
    path = tmp_path / "power.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            MEMBER,
            json.dumps(
                {
                    "DEVICE_ID": 7303,
                    "DEVICE_BD_ID": 1,
                    "data": [
                        {
                            "ITEM_NAME": "R상전류",
                            "ITEM_VALUE": v,
                            "TIMESTAMP": "2021-02-03 07:01:07",
                        }
                        for v in values
                    ],
                },
                ensure_ascii=False,
            ),
        )
    return path


def _binding():
    return PowerHistoryBinding(
        source_id="research-source",
        asset_id="explicit-research-group",
        device_id="7303",
        device_board_id="1",
        timezone="Asia/Seoul",
        identity_evidence="user-assigned research grouping, not verified physical identity",
        timezone_evidence="explicit normalization assumption, not a source fact",
        version="v1",
    )


def test_raw_history_roundtrip_preserves_null_conflicts_and_assumptions(tmp_path):
    archive = _archive(tmp_path)
    records = tuple(iter_power_observations(archive, MEMBER))
    assert [r.value for r in records] == [1.0, None, 2.0]
    assert records[0].device_id == "7303"
    assert records[0].timestamp_text == "2021-02-03 07:01:07"
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    first = import_history(
        archive, MEMBER, _binding(), LOCAL, LOCAL + timedelta(seconds=1), history
    )
    again = import_history(
        archive, MEMBER, _binding(), LOCAL, LOCAL + timedelta(seconds=1), history
    )
    assert first["event_count"] == 3
    assert first["snapshot_id"] > 0
    assert again["recovered_batch_count"] == 1
    assert first["snapshot_id"] == again["snapshot_id"]
    restored = history.query_file_events("research-source")
    assert [r.value for r in restored] == [1.0, None, 2.0]
    metadata = json.loads(restored[0].source_metadata_json)
    assert metadata["raw_timestamp"] == "2021-02-03 07:01:07"
    assert metadata["binding"]["timezone_evidence"] == _binding().timezone_evidence
    assert metadata["semantics"]["definition"]["unit"] is None
    assert metadata["schema"] == "aihub-239-history-v2"
    assert metadata["semantics"]["definition"]["observed_property"] is None
    assert "property_name" not in metadata["semantics"]["definition"]
    page = history.query_measurement_page(
        _binding().asset_id,
        start_at=UTC_START,
        end_at=UTC_START + timedelta(seconds=1),
        channel_id="R상전류",
        point_budget=1,
    )
    assert page.truncated
    assert len(page.points) == 1
    # A conflict beyond the returned row budget must not disappear.
    assert page.points[0].conflicting_duplicate
    rows = measurement_history_rows(page)
    assert rows[0]["unit"] == "unknown"
    assert rows[0]["source_sha256"] == first["archive_sha256"]
    assert rows[0]["identity_evidence"] == _binding().identity_evidence
    assert history.list_history_assets()[0].measurement_count == 3
    assert history.list_history_channels(_binding().asset_id) == ("R상전류",)
    latest = history.query_latest_measurements(_binding().asset_id, channel_id="R상전류")
    assert len(latest) == 1
    assert latest[0].conflicting_duplicate
    assert json.loads(latest[0].source_metadata_json)["binding"] == metadata["binding"]
    latest_row = latest_measurement_rows(latest, as_of=UTC_START + timedelta(seconds=10))[0]
    assert latest_row["value"] is None
    assert latest_row["conflict"] is True
    assert latest_row["event_time_state"] == "recorded"
    assert latest_row["unit"] == "unknown"
    assert latest_row["source_sha256"] == first["archive_sha256"]
    assert latest_row["source_file"] == f"power.zip!/{MEMBER}"
    assert latest_row["timezone_evidence"] == _binding().timezone_evidence
    assert latest_row["identity_evidence"] == _binding().identity_evidence
    assert latest_row["binding_version"] == _binding().version
    assert latest_row["event_time_basis"] == "source-timestamp"
    with pytest.raises(ValueError, match="already exists"):
        import_history(archive, MEMBER, _binding(), LOCAL, LOCAL + timedelta(seconds=2), history)


def test_reader_rejects_invalid_numeric_values_and_binding_guesses(tmp_path):
    archive = _archive(tmp_path, (True,))
    with pytest.raises(ValueError, match="ITEM_VALUE"):
        tuple(iter_power_observations(archive, MEMBER))
    archive = _archive(tmp_path, (1,))
    record = next(iter_power_observations(archive, MEMBER))
    kwargs = dict(archive=archive, archive_digest="a" * 64, archive_bytes=archive.stat().st_size)
    with pytest.raises(ValueError, match="identifiers"):
        project_power_observation(record, binding=replace(_binding(), device_id="391"), **kwargs)
    for timestamp in ("2021-11-07 01:30:00", "2021-03-14 02:30:00"):
        with pytest.raises(ValueError, match="local time"):
            project_power_observation(
                replace(record, timestamp_text=timestamp),
                binding=replace(_binding(), timezone="America/New_York"),
                **kwargs,
            )


def test_profile_counts_null_as_conflicting_value_and_keeps_scope(tmp_path):
    result = profile_archive(_archive(tmp_path, (1, 1, None, 2)))
    member = result["members"][0]
    assert member["record_count"] == 4
    assert member["nulls"] == {"R상전류": 1}
    assert member["duplicate_extra_records"] == 3
    assert member["conflicting_timestamp_channel_groups"] == 1
    assert result["timezone"] is None


def test_existing_catalog_migration_preserves_retry_and_accepts_null(tmp_path):
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    event = FileBackfillEvent(
        raw_evidence_id="old",
        source_id="file",
        asset_id="asset",
        channel_id="channel",
        source_file="old.csv",
        source_sha256="b" * 64,
        source_size_bytes=10,
        sample_index=0,
        event_at=UTC_START,
        value=1.0,
    )
    old_commit = history.append_file_batch((event,), batch_id="old-batch")
    # Recreate the previous persisted schema, not a second validator.
    connection = history._connect()
    try:
        connection.execute(
            "ALTER TABLE phm_history.raw.file_measurement DROP COLUMN source_metadata_json"
        )
        connection.execute(
            "ALTER TABLE phm_history.raw.file_measurement ALTER COLUMN value SET NOT NULL"
        )
    finally:
        connection.close()
    assert history.get_file_batch_commit((event,), batch_id="old-batch") == old_commit
    history.append_file_batch(
        (replace(event, raw_evidence_id="null", sample_index=1, value=None),),
        batch_id="nullable-batch",
    )
    assert len(history.query_file_events("file")) == 2
    assert history.query_file_events("file")[1].value is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_file_raw_rejects_nonfinite_and_boolean_values(value):
    with pytest.raises(ValueError, match="finite numeric"):
        FileBackfillEvent(
            raw_evidence_id="raw",
            source_id="file",
            asset_id="asset",
            channel_id="channel",
            source_file="source",
            source_sha256="a" * 64,
            source_size_bytes=1,
            sample_index=0,
            event_at=UTC_START,
            value=value,
        )


def test_legacy_import_retries_without_rewriting_persisted_semantic_evidence(tmp_path):
    archive = _archive(tmp_path, (1.0,))
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    args = (archive, MEMBER, _binding(), LOCAL, LOCAL + timedelta(seconds=1), history)
    first = import_history(*args, metadata_schema="v1")
    original = history.query_file_events("research-source")[0].source_metadata_json
    assert json.loads(original)["semantics"]["definition"]["property_name"] == "R상전류"
    retry = import_history(*args, metadata_schema="v1")
    assert retry["snapshot_id"] == first["snapshot_id"]
    assert retry["recovered_batch_count"] == 1
    # A new interpretation must not silently mutate immutable imported evidence.
    with pytest.raises(ValueError):
        import_history(*args)
    assert history.query_file_events("research-source")[0].source_metadata_json == original
    latest = history.query_latest_measurements(_binding().asset_id, channel_id="R상전류")
    assert latest_measurement_rows(latest, as_of=UTC_START)[0]["observed_property"] == "unresolved"


def test_bounded_aggregation_covers_full_range_and_preserves_excluded_counts(tmp_path):
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    events = tuple(
        FileBackfillEvent(
            raw_evidence_id=f"row-{i}",
            source_id="file",
            asset_id="asset",
            channel_id="power",
            source_file="series.csv",
            source_sha256="a" * 64,
            source_size_bytes=100,
            sample_index=i,
            event_at=UTC_START + timedelta(seconds=i),
            value=float(i),
        )
        for i in range(2500)
    )
    # Equal repeats remain observations; conflicting values and null remain evidence.
    extras = (
        replace(events[0], raw_evidence_id="repeat", sample_index=2500),
        replace(events[1], raw_evidence_id="conflict", sample_index=2501, value=99.0),
        replace(
            events[2],
            raw_evidence_id="null",
            sample_index=2502,
            event_at=UTC_START + timedelta(seconds=2500),
            value=None,
        ),
        replace(events[0], raw_evidence_id="other-source", source_id="other", value=10000.0),
        replace(
            events[0],
            raw_evidence_id="new-meaning",
            sample_index=2503,
            event_at=UTC_START + timedelta(seconds=2501),
            source_metadata_json=json.dumps(
                {"semantics": {"version": "v2", "definition": {"unit": "kW"}}}
            ),
        ),
    )
    history.append_file_batch(events + extras, batch_id="population")
    result = history.query_measurement_aggregation(
        "asset",
        channel_id="power",
        start_at=UTC_START,
        end_at=UTC_START + timedelta(seconds=2502),
        bucket_count=10,
    )
    assert len(result.buckets) <= 12
    assert sum(b.observation_count for b in result.buckets) == 2505
    assert sum(b.null_count for b in result.buckets) == 1
    assert sum(b.conflict_count for b in result.buckets) == 2
    assert sum(b.usable_count for b in result.buckets) == 2502
    assert max(b.last_event_at for b in result.buckets) == extras[-1].event_at
    assert result.snapshot_id == history.current_snapshot_id()
    assert all(b.bucket_start < b.bucket_end <= result.end_at for b in result.buckets)
    summary = measurement_aggregation_summary(result)
    assert datetime.fromisoformat(summary["returned_end"]) == extras[-1].event_at
    assert summary["observation_count"] == 2505
    first = next(b for b in result.buckets if b.source_id == "file" and b.bucket_start == UTC_START)
    assert first.minimum == 0
    assert first.maximum == 250
    assert first.mean == pytest.approx((sum(range(251)) - 1) / 251)
    assert any('"unit":"kW"' in b.interpretation_json for b in result.buckets)
    empty = history.query_measurement_aggregation(
        "empty", channel_id="power", start_at=UTC_START, end_at=UTC_START + timedelta(days=1)
    )
    assert empty.buckets == ()


def test_aggregation_refuses_to_drop_source_groups_over_response_budget(tmp_path):
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"row-{i}",
                source_id=f"source-{i}",
                asset_id="asset",
                channel_id="power",
                source_file="series.csv",
                source_sha256="a" * 64,
                source_size_bytes=100,
                sample_index=i,
                event_at=UTC_START,
                value=float(i),
            )
            for i in range(2001)
        ),
        batch_id="many-sources",
    )
    with pytest.raises(ValueError, match="exceeds 2000"):
        history.query_measurement_aggregation(
            "asset",
            channel_id="power",
            start_at=UTC_START,
            end_at=UTC_START + timedelta(days=1),
            bucket_count=1,
        )
