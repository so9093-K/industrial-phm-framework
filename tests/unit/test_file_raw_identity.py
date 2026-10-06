"""FILE raw identity contract that keeps the Asset History duplicate check bounded.

Equal raw_evidence_id must imply equal (source_id, source_sha256, sample_index); the
history duplicate lookup is scoped by those columns.
"""

from pathlib import Path

from industrial_phm.adapters.aihub_power import PowerObservation
from industrial_phm.adapters.aihub_power_history import (
    PowerHistoryBinding,
    project_power_observation,
)
from industrial_phm.application.backfill import _file_raw_evidence_id

DIGEST = "a" * 64


def _binding(source_id: str = "device-a") -> PowerHistoryBinding:
    return PowerHistoryBinding(
        source_id=source_id,
        asset_id="asset",
        device_id="1338",
        device_board_id="1",
        timezone="Asia/Seoul",
        identity_evidence="test grouping",
        timezone_evidence="test assumption",
        version="test-v1",
    )


def _record(record_index: int = 7) -> PowerObservation:
    return PowerObservation(
        member="3.공기압축기/SourceData_16.json",
        record_index=record_index,
        device_id="1338",
        device_board_id="1",
        channel_name="R상전류",
        timestamp_text="2020-11-16 04:00:06",
        value=1.0,
        raw_record_json="{}",
    )


def _aihub_event(*, source_id="device-a", digest=DIGEST, record_index=7):
    return project_power_observation(
        _record(record_index),
        archive=Path("3.공기압축기.zip"),
        archive_digest=digest,
        archive_bytes=1,
        binding=_binding(source_id),
    )


def test_aihub_raw_identity_carries_the_scoping_columns() -> None:
    event = _aihub_event()
    assert (event.source_id, event.source_sha256, event.sample_index) == ("device-a", DIGEST, 7)
    # Same identity inputs give the same ID; changing any scoping column changes it.
    assert _aihub_event().raw_evidence_id == event.raw_evidence_id
    assert _aihub_event(source_id="device-b").raw_evidence_id != event.raw_evidence_id
    assert _aihub_event(digest="b" * 64).raw_evidence_id != event.raw_evidence_id
    assert _aihub_event(record_index=8).raw_evidence_id != event.raw_evidence_id


def test_csv_raw_identity_carries_the_scoping_columns() -> None:
    base = {
        "source_id": "file-source",
        "source_file": "history.csv",
        "source_sha256": DIGEST,
        "sample_index": 3,
        "channel_id": "vibration_x",
    }
    identity = _file_raw_evidence_id(**base)
    assert _file_raw_evidence_id(**base) == identity
    for field, value in (("source_id", "other"), ("source_sha256", "b" * 64), ("sample_index", 4)):
        assert _file_raw_evidence_id(**{**base, field: value}) != identity
