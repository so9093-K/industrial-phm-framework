import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec, module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileBackfillEvent,
    FileSourceConfig,
    HistoricalBatchConflictError,
    HistoryIngestionMode,
    InMemorySourceRepository,
    JsonSourceRepository,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    RegisteredSource,
    backfill_registered_file_source,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.cli import main
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

BASE = datetime(2026, 9, 28, 1, 0, tzinfo=UTC)


def _require_duckdb() -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")


def _event(
    *,
    channel_id: str,
    event_at: datetime,
    event_index: int,
    replayed: bool = False,
    value: float | None = None,
    semantic_binding: object = None,
) -> object:
    received_at = event_at + timedelta(milliseconds=20)
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=1.25 + event_index if value is None else value,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=event_at + timedelta(milliseconds=5),
        received_at=received_at,
    )
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=event_index,
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=replayed,
        ),
        semantic_binding=semantic_binding,
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=2,
        event_index=event_index,
        ingested_at=received_at + timedelta(milliseconds=5),
        event_time_policy=OpcUaEventTimePolicy(
            allow_server_timestamp_fallback=True,
        ),
    )


def test_batch_provenance_sidecar_is_rebuildable_and_not_source_of_truth(tmp_path) -> None:
    _require_duckdb()
    catalog = tmp_path / "catalog.sqlite"
    repository = DuckLakeAssetHistory(DuckLakeAssetHistoryConfig(catalog, tmp_path / "data"))
    event = _event(
        channel_id="vibration_x",
        event_at=BASE,
        event_index=1,
    )
    result = repository.append_or_recover_opcua_batch((event,), batch_id="indexed-batch")
    assert result.recovered_existing_commit is False

    index_path = catalog.with_name(catalog.name + ".phm-batch-index.sqlite")
    assert index_path.is_file()

    def indexed_snapshot_id() -> int:
        connection = sqlite3.connect(index_path)
        try:
            row = connection.execute(
                "SELECT snapshot_id FROM batch_provenance_index WHERE batch_id = ?",
                ["indexed-batch"],
            ).fetchone()
        finally:
            connection.close()
        assert row is not None
        return int(row[0])

    assert indexed_snapshot_id() == result.commit.snapshot_id

    index_path.unlink()
    reopened = DuckLakeAssetHistory(DuckLakeAssetHistoryConfig(catalog, tmp_path / "data"))
    recovered = reopened.append_or_recover_opcua_batch((event,), batch_id="indexed-batch")
    assert recovered.recovered_existing_commit is True
    assert recovered.commit == result.commit
    assert indexed_snapshot_id() == result.commit.snapshot_id

    connection = sqlite3.connect(index_path)
    try:
        connection.execute(
            "UPDATE batch_provenance_index SET snapshot_id = ? WHERE batch_id = ?",
            [result.commit.snapshot_id + 10_000, "indexed-batch"],
        )
        connection.commit()
    finally:
        connection.close()

    restarted = DuckLakeAssetHistory(DuckLakeAssetHistoryConfig(catalog, tmp_path / "data"))
    repaired = restarted.append_or_recover_opcua_batch((event,), batch_id="indexed-batch")
    assert repaired.recovered_existing_commit is True
    assert repaired.commit == result.commit
    assert indexed_snapshot_id() == result.commit.snapshot_id


def test_ducklake_asset_history_round_trip(tmp_path) -> None:
    _require_duckdb()
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )
    repository.initialize()
    repository.initialize()

    first = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=1),
        event_index=0,
    )
    second = _event(
        channel_id="temperature",
        event_at=BASE + timedelta(seconds=2),
        event_index=1,
        replayed=True,
    )

    commit = repository.append_opcua_batch(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )

    assert commit.event_count == 2
    assert commit.snapshot_id >= 0
    assert commit.committed_at.utcoffset() is not None
    assert (tmp_path / "catalog.sqlite").is_file()

    measurements = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert [measurement.channel_id for measurement in measurements] == [
        "vibration_x",
        "temperature",
    ]
    assert all(
        measurement.ingestion_mode == HistoryIngestionMode.LIVE for measurement in measurements
    )

    restored_first = repository.get_opcua_event(
        "source-a",
        connection_epoch=2,
        event_index=0,
    )
    restored_second = repository.get_opcua_event(
        "source-a",
        connection_epoch=2,
        event_index=1,
    )
    assert restored_first == first
    assert restored_second == second
    assert restored_second.event.notification.replayed is True

    assert (
        repository.get_opcua_event(
            "source-a",
            connection_epoch=3,
            event_index=0,
        )
        is None
    )

    recovered = repository.get_opcua_batch_commit(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    assert recovered == commit

    repeated = repository.append_opcua_batch(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    assert repeated == commit

    recovered_result = repository.append_or_recover_opcua_batch(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    assert recovered_result.commit == commit
    assert recovered_result.recovered_existing_commit is True

    changed_first = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=10),
        event_index=0,
    )
    with pytest.raises(HistoricalBatchConflictError, match="commit provenance"):
        repository.append_opcua_batch(
            (changed_first, second),
            batch_id="batch-1",
            ingestion_mode=HistoryIngestionMode.LIVE,
        )

    with pytest.raises(ValueError, match="historical delivery already exists"):
        repository.append_opcua_batch(
            (first,),
            batch_id="batch-2",
            ingestion_mode=HistoryIngestionMode.LIVE,
        )


def test_ducklake_asset_history_backfill_provenance(tmp_path) -> None:
    _require_duckdb()
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )
    event = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=3),
        event_index=2,
    )

    repository.append_opcua_batch(
        (event,),
        batch_id="backfill-1",
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    )

    measurement = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )[0]
    assert measurement.ingestion_mode == HistoryIngestionMode.BACKFILL

    live = _event(
        channel_id="temperature",
        event_at=BASE + timedelta(seconds=4),
        event_index=3,
    )
    later_commit = repository.append_opcua_batch(
        (live,),
        batch_id="live-after-backfill",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    recovered_backfill = repository.get_opcua_batch_commit(
        (event,),
        batch_id="backfill-1",
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    )
    assert recovered_backfill is not None
    assert recovered_backfill.snapshot_id < later_commit.snapshot_id


def test_ducklake_file_backfill_and_live_share_asset_history(tmp_path) -> None:
    _require_duckdb()
    source_path = tmp_path / "historical.csv"
    source_path.write_text(
        "timestamp,vibration_x\n2026-09-28T01:00:01+00:00,10.0\n2026-09-28T01:00:02+00:00,11.0\n",
        encoding="utf-8",
    )
    sources = InMemorySourceRepository()
    sources.register(
        RegisteredSource(
            source_id="file-source",
            name="Historical vibration",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id="pump-01",
                measurement_point_id="drive-end",
                channel_columns=("vibration_x",),
                timestamp_column="timestamp",
            ),
            registered_at=BASE,
        )
    )
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )

    backfill = backfill_registered_file_source(
        sources,
        repository,
        "file-source",
    )
    assert backfill.event_count == 2
    assert backfill.recovered_segment_count == 0

    live = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=2),
        event_index=9,
    )
    repository.append_opcua_batch(
        (live,),
        batch_id="live-overlap",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )

    measurements = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert len(measurements) == 3
    assert {item.ingestion_mode for item in measurements} == {
        HistoryIngestionMode.BACKFILL,
        HistoryIngestionMode.LIVE,
    }
    assert {item.source_type.value for item in measurements} == {"file", "opcua"}
    overlap = [item for item in measurements if item.event_at == BASE + timedelta(seconds=2)]
    assert len(overlap) == 2
    assert {item.source_id for item in overlap} == {"file-source", "source-a"}

    page = repository.query_measurement_page(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        channel_id="vibration_x",
    )
    assert len(page.points) == 3
    assert not page.truncated
    assert not any(point.conflicting_duplicate for point in page.points)

    raw_file_events = repository.query_file_events("file-source")
    assert len(raw_file_events) == 2
    assert raw_file_events[0].source_file == "historical.csv"
    assert raw_file_events[0].value == 10.0
    assert raw_file_events[1].value == 11.0

    repeated = backfill_registered_file_source(
        sources,
        repository,
        "file-source",
    )
    assert repeated.recovered_segment_count == 1
    assert (
        len(
            repository.query_measurements(
                "pump-01",
                start_at=BASE,
                end_at=BASE + timedelta(minutes=1),
            )
        )
        == 3
    )
    assert repeated.history_snapshot_id >= backfill.history_snapshot_id

    source_path.write_text(
        "timestamp,vibration_x\n2026-09-28T01:00:01+00:00,20.0\n2026-09-28T01:00:02+00:00,21.0\n",
        encoding="utf-8",
    )
    changed_snapshot = backfill_registered_file_source(
        sources,
        repository,
        "file-source",
    )
    assert changed_snapshot.recovered_segment_count == 0
    assert changed_snapshot.segments[0].batch_id != backfill.segments[0].batch_id

    after_change = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert len(after_change) == 5
    same_file_time = [
        item
        for item in after_change
        if item.source_id == "file-source" and item.event_at == BASE + timedelta(seconds=2)
    ]
    assert len(same_file_time) == 2
    assert {item.value for item in same_file_time} == {11.0, 21.0}
    assert len({item.raw_evidence_id for item in same_file_time}) == 2


def test_backfill_source_cli_reports_snapshot_and_recovers(tmp_path, capsys) -> None:
    _require_duckdb()
    source_path = tmp_path / "historical.csv"
    source_path.write_text(
        "timestamp,vibration_x\n2026-09-28T01:00:01+00:00,1.0\n2026-09-28T01:00:02+00:00,2.0\n",
        encoding="utf-8",
    )
    registry_path = tmp_path / "sources.json"
    registry = JsonSourceRepository(registry_path)
    registry.register(
        RegisteredSource(
            source_id="file-source",
            name="Historical vibration",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id="pump-01",
                measurement_point_id="drive-end",
                channel_columns=("vibration_x",),
                timestamp_column="timestamp",
            ),
            registered_at=BASE,
        )
    )
    args = [
        "maintenance",
        "history",
        "backfill",
        "--registry",
        str(registry_path),
        "--source-id",
        "file-source",
        "--ducklake-catalog",
        str(tmp_path / "catalog.sqlite"),
        "--ducklake-data",
        str(tmp_path / "data"),
    ]

    assert main(args) == 0
    first = capsys.readouterr().out
    assert "state=committed" in first
    assert "history_snapshot=" in first
    assert "input_start=" in first
    assert "input_end=" in first

    assert main(args) == 0
    second = capsys.readouterr().out
    assert "state=recovered" in second


def test_aggregate_excludes_protocol_non_good_and_keeps_empty_numeric_bucket(tmp_path):
    from dataclasses import replace

    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    good = _event(channel_id="power", event_at=BASE, event_index=0)
    original = _event(channel_id="power", event_at=BASE + timedelta(seconds=5), event_index=1)
    observation = replace(
        original.event.notification.observation,
        status_good=False,
        status_code=0x80000000,
        status_text="Bad",
        value=None,
    )
    bad = replace(
        original,
        event=replace(
            original.event,
            notification=replace(original.event.notification, observation=observation),
        ),
    )
    history.append_opcua_batch((good, bad), batch_id="quality")
    result = history.query_measurement_aggregation(
        "pump-01",
        channel_id="power",
        start_at=BASE,
        end_at=BASE + timedelta(seconds=10),
        bucket_count=2,
    )
    assert result.buckets[0].mean == 1.25
    assert result.buckets[1].observation_count == 1
    assert result.buckets[1].non_good_count == 1
    assert result.buckets[1].usable_count == 0
    assert result.buckets[1].mean is None
    assert result.buckets[1].minimum is None
    assert result.buckets[1].maximum is None


def test_flush_moves_inlined_rows_without_changing_snapshot_evidence(tmp_path, capsys):
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    events = tuple(
        _event(channel_id="power", event_at=BASE + timedelta(seconds=i), event_index=i)
        for i in range(3)
    )
    first = history.append_opcua_batch(events[:2], batch_id="first")
    second = history.append_opcua_batch(events[2:], batch_id="second")
    before = history.query_opcua_events("source-a")
    assert not list((tmp_path / "data").rglob("*.parquet"))

    args = [
        "maintenance",
        "history",
        "flush",
        "--ducklake-catalog",
        str(tmp_path / "catalog.sqlite"),
        "--ducklake-data",
        str(tmp_path / "data"),
    ]
    assert main(args) == 0
    output = capsys.readouterr().out
    assert "table=history.measurement flushed_rows=3" in output
    assert list((tmp_path / "data").rglob("*.parquet"))
    flushed_snapshot = history.current_snapshot_id()
    assert flushed_snapshot > second.snapshot_id

    assert history.query_opcua_events("source-a") == before
    # Batch recovery and time travel stay bound to the original commit snapshots.
    assert history.get_opcua_batch_commit(events[:2], batch_id="first") == first
    connection = history._connect()
    try:
        for commit, expected in ((first, 2), (second, 3)):
            count = connection.execute(
                "SELECT count(*) FROM phm_history.history.measurement "
                f"AT (VERSION => {commit.snapshot_id})"
            ).fetchone()
            assert count == (expected,)
    finally:
        connection.close()

    # Nothing left to move: no new snapshot, so exact retries report the same state.
    assert main(args) == 0
    assert "flushed_rows=0" in capsys.readouterr().out
    assert history.current_snapshot_id() == flushed_snapshot


def test_compaction_preserves_snapshot_evidence_and_batch_recovery(tmp_path, capsys):
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    commits = []
    batches = []
    for batch_index in range(8):
        events = tuple(
            _event(
                channel_id=f"channel-{event_index % 3}",
                event_at=BASE + timedelta(seconds=batch_index, milliseconds=event_index),
                event_index=batch_index * 10 + event_index,
            )
            for event_index in range(3)
        )
        batches.append(events)
        commits.append(history.append_opcua_batch(events, batch_id=f"compact-{batch_index}"))
        history.flush_inlined_data()

    runtime = history.runtime_fingerprint()
    assert runtime.duckdb_version
    assert runtime.ducklake_extension_version

    before = history.inspect_storage()
    assert before.active_data_file_count >= 8
    snapshots = (commits[0].snapshot_id, commits[3].snapshot_id, commits[-1].snapshot_id)
    fingerprints = {
        snapshot_id: history.snapshot_evidence_fingerprint(snapshot_id) for snapshot_id in snapshots
    }

    result = history.compact_adjacent_files(
        max_compacted_files=32,
        target_file_size_bytes=1024 * 1024,
        max_file_size_bytes=256 * 1024,
    )
    assert result.snapshot_before == before.current_snapshot_id
    assert result.snapshot_after >= result.snapshot_before
    assert result.files_processed > result.files_created > 0
    assert result.storage_after.active_data_file_count < before.active_data_file_count
    # Merge-only compaction schedules replaced files but deliberately does not delete them.
    assert result.storage_after.scheduled_for_deletion_count > before.scheduled_for_deletion_count
    assert result.storage_after.physical_parquet_file_count >= before.physical_parquet_file_count

    reopened = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    for snapshot_id, fingerprint in fingerprints.items():
        assert reopened.snapshot_evidence_fingerprint(snapshot_id) == fingerprint

    assert reopened.get_opcua_batch_commit(batches[0], batch_id="compact-0") == commits[0]
    assert reopened.append_opcua_batch(batches[0], batch_id="compact-0") == commits[0]

    next_event = _event(
        channel_id="channel-next",
        event_at=BASE + timedelta(minutes=1),
        event_index=999,
    )
    next_commit = reopened.append_opcua_batch((next_event,), batch_id="after-compact")
    assert next_commit.snapshot_id > result.snapshot_after
    assert reopened.get_opcua_batch_commit((next_event,), batch_id="after-compact") == next_commit

    args = [
        "maintenance",
        "history",
        "compact",
        "--ducklake-catalog",
        str(tmp_path / "catalog.sqlite"),
        "--ducklake-data",
        str(tmp_path / "data"),
        "--max-compacted-files",
        "32",
        "--target-file-size-bytes",
        str(1024 * 1024),
        "--max-file-size-bytes",
        str(256 * 1024),
    ]
    assert main(args) == 0
    output = capsys.readouterr().out
    assert "duckdb=" in output
    assert "snapshot_before=" in output
    assert "scheduled_for_deletion_after=" in output


def test_compaction_uses_same_catalog_lease_and_times_out_explicitly(tmp_path):
    filelock = pytest.importorskip("filelock")
    _require_duckdb()
    catalog = tmp_path / "catalog.sqlite"
    data = tmp_path / "data"
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog,
            data,
            catalog_lock_timeout_seconds=0.01,
        )
    )
    history.initialize()
    external_lock = filelock.FileLock(str(catalog) + ".phm.lock")
    external_lock.acquire()
    try:
        with pytest.raises(TimeoutError, match="timed out waiting for local history catalog"):
            history.compact_adjacent_files(
                max_compacted_files=1,
                target_file_size_bytes=1024 * 1024,
            )
    finally:
        external_lock.release()


def test_compaction_rejects_unbounded_or_invalid_limits(tmp_path):
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    with pytest.raises(ValueError, match="at least 1"):
        history.compact_adjacent_files(
            max_compacted_files=0,
            target_file_size_bytes=1024 * 1024,
        )
    with pytest.raises(ValueError, match="less than"):
        history.compact_adjacent_files(
            max_compacted_files=1,
            target_file_size_bytes=1024 * 1024,
            min_file_size_bytes=100,
            max_file_size_bytes=100,
        )


def test_batch_insert_leaves_import_state_unchanged(tmp_path):
    import sys

    _require_duckdb()
    had_pandas = "pandas" in sys.modules
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    event = _event(channel_id="power", event_at=BASE, event_index=0)
    history.append_opcua_batch((event,), batch_id="import-state")
    # The absent-pandas cache is scoped to one bind and must not leak a None module.
    assert ("pandas" in sys.modules) == had_pandas
    assert history.query_opcua_events("source-a") == (event,)


def _phase_binding(channel_id: str, phase: str, quantity: str, unit: str) -> object:
    from industrial_phm.application.measurement_semantics import (
        ChannelSemanticBinding,
        MeasurementDefinition,
    )

    return ChannelSemanticBinding(
        source_id="source-a",
        channel_id=channel_id,
        version="site-semantics-v1",
        definition=MeasurementDefinition(
            quantity, scope=f"phase {phase}", unit=unit, unit_evidence="meter nameplate"
        ),
        interpretation_evidence="commissioning record",
    )


def test_opcua_semantic_snapshot_reaches_raw_evidence_and_analysis_input(tmp_path):
    from industrial_phm.application.phase_unbalance import (
        PhaseUnbalanceConfig,
        run_phase_unbalance_analysis,
    )

    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    channels = {
        "va": ("R", "phase voltage", "V", 220.0),
        "vb": ("S", "phase voltage", "V", 230.0),
        "vc": ("T", "phase voltage", "V", 225.0),
        "ia": ("R", "phase current", "A", 10.0),
        "ib": ("S", "phase current", "A", 10.0),
        # Registered without a binding: must stay unresolved, never inferred.
        "ic": ("T", None, None, 13.0),
    }
    events = tuple(
        _event(
            channel_id=channel,
            event_at=BASE,
            event_index=index,
            value=value,
            semantic_binding=(
                None if quantity is None else _phase_binding(channel, phase, quantity, unit)
            ),
        )
        for index, (channel, (phase, quantity, unit, value)) in enumerate(channels.items())
    )
    commit = history.append_opcua_batch(events, batch_id="semantic")

    # The raw evidence restores the exact snapshot (window rebuilds read this path).
    assert history.query_opcua_events("source-a") == events
    assert history.get_opcua_batch_commit(events, batch_id="semantic") == commit

    analysis = run_phase_unbalance_analysis(
        history,
        asset_id="pump-01",
        source_id="source-a",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        config=PhaseUnbalanceConfig(("va", "vb", "vc"), ("ia", "ib", "ic")),
    )
    voltage, current = analysis.evidence.results
    assert voltage.evaluated_samples == 1
    assert voltage.median_percent == pytest.approx(5 / 225 * 100)
    assert analysis.evidence.semantic_versions == ("site-semantics-v1",)
    assert current.evaluated_samples == 0
    assert current.excluded_samples == {"unconfirmed-semantics": 1}

    # Without explicit names the channels are found by their bound roles.
    by_role = run_phase_unbalance_analysis(
        history,
        asset_id="pump-01",
        source_id="source-a",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    role_voltage, role_current = by_role.evidence.results
    assert role_voltage.channels == ("va", "vb", "vc")
    assert role_voltage.channel_selection == "semantic-role"
    assert role_voltage.median_percent == voltage.median_percent
    assert role_current.channel_selection == "unresolved"

    # History screens show the same OPC UA meaning the analysis used.
    from industrial_phm.presentation.measurement_history import (
        latest_measurement_rows,
        measurement_aggregation_rows,
        measurement_history_rows,
    )

    latest_asset = history.query_latest_asset_measurements("pump-01")
    assert tuple(point.measurement.channel_id for point in latest_asset) == tuple(sorted(channels))
    latest_asset_rows = latest_measurement_rows(
        latest_asset,
        as_of=BASE + timedelta(minutes=1),
    )
    assert {row["channel"]: row["unit"] for row in latest_asset_rows}["va"] == "V"
    assert {row["channel"]: row["observed_property"] for row in latest_asset_rows}["ic"] == (
        "unresolved"
    )

    multi_signal = history.query_multi_signal_measurement_aggregation(
        "pump-01",
        channel_ids=("va", "ia"),
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        bucket_count=2,
    )
    assert {bucket.channel_id for bucket in multi_signal.buckets} == {"va", "ia"}
    assert {
        (bucket.channel_id, bucket.mean) for bucket in multi_signal.buckets if bucket.usable_count
    } == {("va", 220.0), ("ia", 10.0)}
    assert {bucket.bucket_start for bucket in multi_signal.buckets} == {BASE}

    def shown(channel):
        latest = history.query_latest_measurements("pump-01", channel_id=channel)
        (row,) = latest_measurement_rows(latest, as_of=BASE + timedelta(minutes=1))
        return row["observed_property"], row["unit"], row["semantic_version"]

    assert shown("va") == ("phase voltage", "V", "site-semantics-v1")
    assert shown("ic")[:2] == ("unresolved", "unknown")
    page = history.query_measurement_page(
        "pump-01", start_at=BASE, end_at=BASE + timedelta(minutes=1), channel_id="ia"
    )
    assert measurement_history_rows(page)[0]["unit"] == "A"
    aggregation = history.query_measurement_aggregation(
        "pump-01",
        channel_id="va",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        bucket_count=1,
    )
    aggregation_rows = measurement_aggregation_rows(aggregation)
    assert len(aggregation_rows) == 1
    assert aggregation_rows[0]["observed_property"] == "phase voltage"
    assert aggregation_rows[0]["unit"] == "V"

    # A stored snapshot naming another channel must not lend its meaning to this row.
    connection = history._connect()
    try:
        connection.execute(
            "UPDATE phm_history.raw.opcua_data_change SET semantic_binding_json = ("
            "SELECT semantic_binding_json FROM phm_history.raw.opcua_data_change "
            "WHERE channel_id = 'vb') WHERE channel_id = 'va'"
        )
    finally:
        connection.close()
    observations = history.query_channel_observations(
        "pump-01",
        source_id="source-a",
        channel_ids=("va", "vb"),
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        snapshot_id=history.current_snapshot_id(),
    )
    assert {o.channel_id: o.observed_property for o in observations} == {
        "va": None,
        "vb": "phase voltage",
    }
    assert shown("va")[:2] == ("unresolved", "unknown")
    changed_aggregation = history.query_measurement_aggregation(
        "pump-01",
        channel_id="va",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        bucket_count=1,
    )
    changed_rows = measurement_aggregation_rows(changed_aggregation)
    assert len(changed_rows) == 1
    assert changed_rows[0]["observed_property"] == "unresolved"
    assert changed_rows[0]["unit"] == "unknown"


def test_snapshot_before_semantic_column_reads_as_unresolved(tmp_path):
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    event = _event(channel_id="power", event_at=BASE, event_index=0)
    history.append_opcua_batch((event,), batch_id="before")
    # Recreate a catalog whose OPC UA table predates semantic snapshots.
    connection = history._connect()
    try:
        connection.execute(
            "ALTER TABLE phm_history.raw.opcua_data_change DROP COLUMN semantic_binding_json"
        )
        (old_snapshot,) = connection.execute(
            "SELECT max(snapshot_id) FROM phm_history.snapshots()"
        ).fetchone()
    finally:
        connection.close()

    # Reopening migrates once; the pre-migration snapshot stays readable.
    assert history.query_opcua_events("source-a") == (event,)
    observations = history.query_channel_observations(
        "pump-01",
        source_id="source-a",
        channel_ids=("power",),
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        snapshot_id=old_snapshot,
    )
    assert [(o.value, o.observed_property) for o in observations] == [(1.25, None)]
    assert history.current_snapshot_id() > old_snapshot


def test_semantics_bearing_batch_committed_before_fingerprint_version_recovers(
    tmp_path, monkeypatch
):
    """#303 wrote spool events with semantics but a semantics-free DuckLake fingerprint.

    A batch committed that way and not acknowledged before a crash must recover after
    upgrade, and its raw rows must not be backfilled with the current semantics.
    """
    from industrial_phm.history import ducklake

    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    binding = _phase_binding("va", "R", "phase voltage", "V")
    events = (_event(channel_id="va", event_at=BASE, event_index=0, semantic_binding=binding),)
    fingerprint = ducklake._opcua_batch_fingerprint
    with monkeypatch.context() as legacy:
        legacy.setattr(ducklake, "_OPCUA_FINGERPRINT_VERSION", None)
        legacy.setattr(
            ducklake,
            "_opcua_batch_fingerprint",
            lambda batch, include_semantics=True: fingerprint(batch, include_semantics=False),
        )
        legacy.setattr(ducklake, "_semantic_binding_json", lambda _binding: None)
        commit = history.append_opcua_batch(events, batch_id="committed-before-ack")

    assert history.get_opcua_batch_commit(events, batch_id="committed-before-ack") == commit
    assert history.append_opcua_batch(events, batch_id="committed-before-ack") == commit
    (restored,) = history.query_opcua_events("source-a")
    assert restored.event.semantic_binding is None

    # Versioned commits still bind the snapshot into the batch identity.
    later = (
        _event(
            channel_id="vb",
            event_at=BASE,
            event_index=1,
            semantic_binding=_phase_binding("vb", "R", "phase voltage", "V"),
        ),
    )
    history.append_opcua_batch(later, batch_id="versioned")
    changed = (
        _event(
            channel_id="vb",
            event_at=BASE,
            event_index=1,
            semantic_binding=_phase_binding("vb", "S", "phase voltage", "V"),
        ),
    )
    with pytest.raises(HistoricalBatchConflictError):
        history.get_opcua_batch_commit(changed, batch_id="versioned")


def _file_event(source_id: str, sample_index: int, *, sha: str = "a" * 64) -> FileBackfillEvent:
    # Mirrors every producer: the raw ID is derived from source, file digest and index.
    return FileBackfillEvent(
        raw_evidence_id=f"file:{source_id}:{sha}:{sample_index}",
        source_id=source_id,
        asset_id="asset-" + source_id,
        channel_id="current",
        source_file="power.zip!/member.json",
        source_sha256=sha,
        source_size_bytes=10,
        sample_index=sample_index,
        event_at=BASE + timedelta(seconds=sample_index),
        value=float(sample_index),
    )


def test_file_duplicate_check_is_scoped_by_source_digest_and_sample_range(tmp_path) -> None:
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    history.append_file_batch(
        tuple(_file_event("device-a", index) for index in range(0, 4)), batch_id="a-0"
    )
    # Another source and another file digest with the same sample range are new evidence.
    history.append_file_batch(
        tuple(_file_event("device-b", index) for index in range(0, 4)), batch_id="b-0"
    )
    history.append_file_batch(
        tuple(_file_event("device-a", index, sha="b" * 64) for index in range(0, 4)),
        batch_id="a-other-file",
    )
    assert len(history.query_file_events("device-a")) == 8

    # A batch mixing sources still finds the one already stored cell of device-a.
    mixed = (
        _file_event("device-b", 10),
        _file_event("device-a", 3),
        _file_event("device-a", 11),
    )
    with pytest.raises(ValueError, match="historical FILE evidence already exists"):
        history.append_file_batch(mixed, batch_id="mixed")
    assert len(history.query_file_events("device-b")) == 4


def test_file_retry_and_duplicate_rejection_survive_reopen_and_compaction(tmp_path) -> None:
    _require_duckdb()
    config = DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    history = DuckLakeAssetHistory(config)
    batch = tuple(_file_event("device-a", index) for index in range(4))
    commit = history.append_file_batch(batch, batch_id="original-file")
    history.append_file_batch(
        tuple(_file_event("device-a", index) for index in range(4, 8)), batch_id="next-file"
    )
    snapshot = history.inspect_storage().current_snapshot_id
    fingerprint = history.snapshot_evidence_fingerprint(snapshot)
    history.compact_adjacent_files(
        max_compacted_files=32,
        target_file_size_bytes=1_048_576,
    )
    reopened = DuckLakeAssetHistory(config)
    current = reopened.inspect_storage().current_snapshot_id
    assert reopened.snapshot_evidence_fingerprint(current) == fingerprint
    assert reopened.snapshot_evidence_fingerprint(snapshot) == fingerprint
    assert reopened.append_file_batch(batch, batch_id="original-file") == commit
    assert len(reopened.query_file_events("device-a")) == 8
    with pytest.raises(ValueError, match="historical FILE evidence already exists"):
        reopened.append_file_batch(batch, batch_id="different-batch")
    changed = (replace(batch[0], value=99.0), *batch[1:])
    with pytest.raises(HistoricalBatchConflictError):
        reopened.append_file_batch(changed, batch_id="original-file")
    assert len(reopened.query_file_events("device-a")) == 8


def test_latest_and_monitor_reads_bound_by_time_keep_stale_channels_and_conflicts(
    tmp_path,
) -> None:
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )

    def event(source_id, index, asset_id, channel_id, seconds, value):
        return replace(
            _file_event(source_id, index),
            asset_id=asset_id,
            channel_id=channel_id,
            event_at=BASE + timedelta(seconds=seconds),
            value=value,
            source_metadata_json=f'{{"binding":{{"channel":"{channel_id}"}}}}',
        )

    history.append_file_batch(
        (
            # The stale channel's latest is far older than the other channel's.
            event("device-a", 0, "pump-01", "current", 0, 10.0),
            event("device-a", 1, "pump-01", "voltage", 0, 220.0),
            event("device-a", 2, "pump-01", "voltage", 600, 221.0),
            # A second value at the latest voltage time is a conflict, not a resolution.
            event("device-a", 3, "pump-01", "voltage", 600, 230.0),
            # Another asset's newer rows must not move or leak into pump-01 reads.
            event("device-b", 0, "pump-02", "voltage", 1200, 999.0),
        ),
        batch_id="latest-bounds",
    )

    latest = history.query_latest_asset_measurements("pump-01")
    assert [
        (
            point.measurement.channel_id,
            point.measurement.event_at,
            point.conflicting_duplicate,
            point.source_file,
            point.source_metadata_json,
        )
        for point in latest
    ] == [
        ("current", BASE, False, "power.zip!/member.json", '{"binding":{"channel":"current"}}'),
        (
            "voltage",
            BASE + timedelta(seconds=600),
            True,
            "power.zip!/member.json",
            '{"binding":{"channel":"voltage"}}',
        ),
    ]
    (stale,) = history.query_latest_measurements("pump-01", channel_id="current")
    assert (stale.measurement.event_at, stale.measurement.value) == (BASE, 10.0)
    assert stale.source_metadata_json == '{"binding":{"channel":"current"}}'
    assert history.query_latest_asset_measurements("pump-03") == ()
    assert history.query_latest_measurements("pump-01", channel_id="absent") == ()

    chart = history.query_multi_signal_measurement_aggregation(
        "pump-01",
        channel_ids=("voltage", "current"),
        start_at=BASE,
        end_at=BASE + timedelta(minutes=30),
        bucket_count=3,
    )
    assert {
        (bucket.channel_id, bucket.maximum, bucket.conflict_count, bucket.interpretation_json)
        for bucket in chart.buckets
    } == {
        ("current", 10.0, 0, '{"binding":{"channel":"current"},"semantics":null}'),
        ("voltage", 220.0, 0, '{"binding":{"channel":"voltage"},"semantics":null}'),
        ("voltage", None, 2, '{"binding":{"channel":"voltage"},"semantics":null}'),
    }


_FILE_SCALING_SPEC = spec_from_file_location(
    "file_append_scaling", Path(__file__).parents[2] / "tools/history/file_append_scaling.py"
)
assert _FILE_SCALING_SPEC is not None and _FILE_SCALING_SPEC.loader is not None
_FILE_SCALING_TOOL = module_from_spec(_FILE_SCALING_SPEC)
_FILE_SCALING_SPEC.loader.exec_module(_FILE_SCALING_TOOL)


def test_preloaded_rows_match_public_event_projection_and_detect_duplicates(tmp_path) -> None:
    pytest.importorskip("duckdb")
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    starts = [34, 69]
    metadata = '{"padding":"test"}'
    _FILE_SCALING_TOOL._preload(history, starts, 7, metadata, seed_id="seed-7")
    assert starts == [38, 72]
    assert history.query_file_events("device-00") == tuple(
        _FILE_SCALING_TOOL._event(0, index, metadata) for index in range(34, 38)
    )
    assert history.query_file_events("device-01") == tuple(
        _FILE_SCALING_TOOL._event(1, index, metadata) for index in range(69, 72)
    )
    points = history.query_measurements(
        "asset-00",
        start_at=_FILE_SCALING_TOOL.BASE,
        end_at=_FILE_SCALING_TOOL.BASE + timedelta(minutes=2),
    )
    assert len(points) == 4
    assert points[0].event_time_basis.value == "source-timestamp"
    with pytest.raises(ValueError, match="historical FILE evidence already exists"):
        history.append_file_batch(
            (_FILE_SCALING_TOOL._event(0, 37, metadata),), batch_id="duplicate"
        )
    history.append_file_batch(
        (_FILE_SCALING_TOOL._event(0, 38, metadata),), batch_id="public-probe"
    )
    assert len(history.query_file_events("device-00")) == 5


def test_compaction_measurements_keep_the_same_row_count(tmp_path) -> None:
    pytest.importorskip("duckdb")
    report = _FILE_SCALING_TOOL.run(
        tmp_path,
        checkpoints=[101],
        sources=2,
        batch_size=5,
        metadata_bytes=32,
        repeats=1,
        compact_at_end=True,
    )
    before, after = report["checkpoints"]
    # One timed probe plus one uncontended and one contended lock-contention append.
    assert before["stored_rows"] == after["stored_rows"] == 116
    assert before["batches"] == after["batches"] == 3
    assert before["active_parquet_files"] >= after["active_parquet_files"]
    assert after["physical_parquet_files"] >= after["active_parquet_files"]
    assert set(before["lock"]) == {
        "monitor_read_lock_hold_ms",
        "append_lock_hold_ms",
        "append_connect_uncontended_ms",
        "append_connect_behind_monitor_read_ms",
    }
    assert after["lock"] is None


def test_fixed_queried_asset_grows_only_unrelated_assets(tmp_path) -> None:
    pytest.importorskip("duckdb")
    report = _FILE_SCALING_TOOL.run(
        tmp_path,
        checkpoints=[0, 200],
        sources=3,
        batch_size=5,
        metadata_bytes=32,
        repeats=1,
        queried_asset_rows=70,
    )
    first, second = report["checkpoints"]
    assert first["queried_asset_rows"] == second["queried_asset_rows"] == 70
    assert second["stored_rows"] == 215
    assert report["workload"]["queried_asset_rows"] == 70
    with pytest.raises(ValueError, match="fixed queried asset"):
        _FILE_SCALING_TOOL.run(
            tmp_path / "invalid",
            checkpoints=[0],
            sources=1,
            batch_size=5,
            metadata_bytes=32,
            repeats=1,
            queried_asset_rows=70,
        )
