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


def test_file_phase_semantics_show_the_saved_definition_and_evidence() -> None:
    raw = (
        '{"binding":null,"semantics":{"channel_id":"R상전압",'
        '"definition":{"observed_property":"phase voltage","scope":"phase R",'
        '"unit":"V","unit_evidence":"provider table and recorded relation"},'
        '"interpretation_evidence":"archive/member; timezone explicitly assumed",'
        '"source_path":"/private/input.csv"}}'
    )
    result = _semantic(raw)
    assert result["unit"] == "V"
    assert result["observed_property"] == "phase voltage"
    assert result["unit_evidence"] == "provider table and recorded relation"
    assert "timezone explicitly assumed" in str(result["interpretation_evidence"])
    assert "private" not in str(result)


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
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for window in ((start, start), (start, start + timedelta(days=32))):
        with pytest.raises(ValueError, match="window must span"):
            project_signal_history(
                None,  # type: ignore[arg-type]
                asset_id="asset-01",
                channel_ids=("voltage-R",),
                window=window,
            )
    with pytest.raises(ValueError, match="explicit timezone"):
        project_signal_history(
            None,  # type: ignore[arg-type]
            asset_id="asset-01",
            channel_ids=("voltage-R",),
            window=(start.replace(tzinfo=None), start.replace(tzinfo=None) + timedelta(hours=1)),
        )


def test_selected_reference_has_a_value_before_new_observations_and_keeps_it_afterward() -> None:
    from dataclasses import replace

    from industrial_phm.runtime.operations_web_signals import _reference_changes

    base = MultiSignalMeasurementHistoryBucket(
        channel_id="current",
        source_id="file-meter",
        source_type="file",
        measurement_point_id=None,
        bucket_start=AT,
        bucket_end=AT + timedelta(minutes=1),
        first_event_at=AT,
        last_event_at=AT,
        observation_count=1,
        usable_count=1,
        null_count=0,
        non_good_count=0,
        conflict_count=0,
        minimum=2.0,
        maximum=2.0,
        mean=2.0,
        interpretation_json='{"binding":{"definition":{"unit":"A"}}}',
    )
    baseline = tuple(
        replace(
            base,
            bucket_start=AT + timedelta(minutes=i),
            bucket_end=AT + timedelta(minutes=i + 1),
            first_event_at=AT + timedelta(minutes=i),
            last_event_at=AT + timedelta(minutes=i),
        )
        for i in range(5)
    )
    period = (AT, AT + timedelta(minutes=5))
    before = _reference_changes((), baseline, period)
    assert before["groups"][0]["state"] == "no-observations-after-reference"
    assert before["groups"][0]["median"] == 2.0
    assert before["groups"][0]["intervals"] == []
    observed = (
        replace(
            base,
            bucket_start=period[1],
            bucket_end=period[1] + timedelta(minutes=1),
            mean=4.0,
            minimum=4.0,
            maximum=4.0,
        ),
    )
    after = _reference_changes(observed, baseline, period)
    assert (after["from"], after["to"]) == (before["from"], before["to"])
    group = after["groups"][0]
    assert group["state"] == "ready" and group["median"] == 2.0
    assert group["intervals"][0]["value"] == 4.0
