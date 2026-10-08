"""Browser-safe quality/semantics projection for bounded signal-history buckets."""

from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.measurement_history import (
    MultiSignalMeasurementHistoryBucket,
)
from industrial_phm.runtime.operations_web_signals import (
    _bucket,
    _semantic,
    project_signal_history,
)

AT = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)


def test_history_semantics_are_allowlisted_not_raw_provider_metadata() -> None:
    raw = (
        '{"binding":{"definition":{"observed_property":"phase voltage",'
        '"unit":"V","scope":"R","source_path":"/secret/file.csv"},'
        '"endpoint_url":"opc.tcp://internal"},"semantics":null,'
        '"token":"private"}'
    )
    semantic = _semantic(raw)
    assert semantic == {"observed_property": "phase voltage", "scope": "R", "unit": "V"}
    assert "secret" not in str(semantic)
    assert "opc.tcp" not in str(semantic)


def test_history_bucket_keeps_source_quality_and_time_without_inventing_gap_points() -> None:
    at = AT - timedelta(minutes=4)
    bucket = MultiSignalMeasurementHistoryBucket(
        channel_id="voltage-R",
        source_id="source-01",
        source_type="opcua",
        measurement_point_id="motor",
        bucket_start=at,
        bucket_end=at + timedelta(minutes=1),
        first_event_at=at + timedelta(seconds=10),
        last_event_at=at + timedelta(seconds=40),
        observation_count=5,
        usable_count=2,
        null_count=1,
        non_good_count=1,
        conflict_count=1,
        minimum=217.1,
        maximum=220.8,
        mean=218.95,
        interpretation_json='{"binding":null,"semantics":null}',
    )
    result = _bucket(bucket)

    assert result["mean"] == 218.95
    assert result["null_count"] == 1
    assert result["non_good_count"] == 1
    assert result["conflict_count"] == 1
    assert result["usable_count"] == 2
    assert result["first_event_at"] == "2026-10-08T09:56:10Z"
    assert result["semantics"] == {
        "observed_property": None,
        "scope": None,
        "unit": None,
    }
    assert "value" not in result
    assert "interpretation_json" not in result


def test_signal_query_validates_requested_groups_before_reading() -> None:
    with pytest.raises(ValueError, match="channel_ids"):
        project_signal_history(
            None,  # type: ignore[arg-type]
            asset_id="asset-01",
            channel_ids=("voltage-R", "voltage-R"),
        )
    with pytest.raises(ValueError, match="unsupported range"):
        project_signal_history(
            None,  # type: ignore[arg-type]
            asset_id="asset-01",
            channel_ids=("voltage-R",),
            range_preset="500d",
        )
    with pytest.raises(ValueError, match="bucket_count"):
        project_signal_history(
            None,  # type: ignore[arg-type]
            asset_id="asset-01",
            channel_ids=("voltage-R",),
            bucket_count=10000,
        )
