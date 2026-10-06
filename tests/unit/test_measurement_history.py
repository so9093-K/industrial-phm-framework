from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from industrial_phm.application.asset_history import (
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
)
from industrial_phm.application.measurement_history import (
    HistoryEventTimeState,
    MeasurementHistoryPoint,
    assess_latest_measurement,
    resolve_measurement_range,
)
from industrial_phm.application.source_registration import SourceType

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def test_event_currency_does_not_infer_value_quality_or_asset_health():
    measurement = HistoricalMeasurement(
        raw_evidence_id="raw",
        source_id="source",
        source_type=SourceType.OPCUA,
        asset_id="asset",
        channel_id="power",
        event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
        event_at=NOW - timedelta(seconds=10),
        value=None,
        status_good=False,
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    point = MeasurementHistoryPoint(measurement, conflicting_duplicate=False)
    assert (
        assess_latest_measurement(point, as_of=NOW).event_time_state
        == HistoryEventTimeState.RECORDED
    )
    assert assess_latest_measurement(point, as_of=NOW).age_seconds == 10
    future = replace(point, measurement=replace(measurement, event_at=NOW + timedelta(seconds=1)))
    status = assess_latest_measurement(future, as_of=NOW)
    assert status.event_time_state == HistoryEventTimeState.FUTURE
    assert status.age_seconds == -1


def test_recent_range_moves_with_each_query_and_custom_range_is_explicit():
    old = NOW - timedelta(days=365)
    start, end = resolve_measurement_range("15m", as_of=NOW, start_at=old, end_at=old)
    assert (start, end) == (NOW - timedelta(minutes=15), NOW)
    assert resolve_measurement_range("1h", as_of=NOW, start_at=old, end_at=old) == (
        NOW - timedelta(hours=1),
        NOW,
    )
    later = NOW + timedelta(minutes=1)
    assert resolve_measurement_range("24h", as_of=later, start_at=old, end_at=old) == (
        later - timedelta(hours=24),
        later,
    )
    with pytest.raises(ValueError, match="increasing"):
        resolve_measurement_range("custom", as_of=NOW, start_at=old, end_at=old)


def test_latest_rows_preserve_known_units_and_expose_missing_event_time():
    import json

    from industrial_phm.presentation.measurement_history import latest_measurement_rows

    measurement = HistoricalMeasurement(
        raw_evidence_id="raw",
        source_id="source",
        source_type=SourceType.FILE,
        asset_id="asset",
        channel_id="power",
        event_time_basis=HistoricalEventTimeBasis.UNAVAILABLE,
        event_at=None,
        value=2.0,
        status_good=True,
        ingestion_mode=HistoryIngestionMode.IMPORT,
    )
    point = MeasurementHistoryPoint(
        measurement,
        conflicting_duplicate=False,
        source_metadata_json=json.dumps(
            {
                "semantics": {
                    "version": "v2",
                    "interpretation_evidence": "instrument documentation",
                    "definition": {
                        "scope": "motor input",
                        "unit": "kW",
                        "unit_evidence": "instrument manual section 4",
                    },
                }
            }
        ),
    )
    row = latest_measurement_rows((point,), as_of=NOW)[0]
    assert row["value"] == 2.0
    assert row["unit"] == "kW"
    assert row["scope"] == "motor input"
    assert row["unit_evidence"] == "instrument manual section 4"
    assert row["semantic_version"] == "v2"
    assert row["event_time_state"] == "time-unavailable"
    assert row["event_time_basis"] == "unavailable"
    assert row["time"] is None
    assert row["history_age_seconds"] is None
    unknown = latest_measurement_rows((replace(point, source_metadata_json=None),), as_of=NOW)[0]
    assert unknown["unit"] == "unknown"
    assert unknown["unit_evidence"] is None


def test_file_presence_is_not_protocol_quality_and_legacy_label_stays_unresolved():
    import json

    from industrial_phm.application.asset_history import MeasurementSourceQuality
    from industrial_phm.presentation.measurement_history import latest_measurement_rows

    measurement = HistoricalMeasurement(
        raw_evidence_id="file",
        source_id="file",
        source_type=SourceType.FILE,
        asset_id="asset",
        channel_id="R상유효전력",
        event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
        event_at=NOW - timedelta(days=2000),
        value=1.0,
        status_good=True,
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    )
    point = MeasurementHistoryPoint(
        measurement,
        False,
        json.dumps(
            {
                "schema": "aihub-239-history-v1",
                "semantics": {"definition": {"property_name": "R상유효전력"}},
            }
        ),
    )
    row = latest_measurement_rows((point,), as_of=NOW)[0]
    assert row["observed_property"] == "unresolved"
    assert row["legacy_property_label"] == measurement.channel_id
    assert row["source_quality"] == "unknown"
    assert row["value_availability"] == "present"
    assert row["history_age_seconds"] == 2000 * 86400
    assert row["expected_live_freshness"] == "not-applicable"
    assert row["event_time_state"] == "recorded"
    null = replace(point, measurement=replace(measurement, value=None, status_good=False))
    null_row = latest_measurement_rows((null,), as_of=NOW)[0]
    assert null_row["source_quality"] == "unknown"
    assert null_row["value_availability"] == "null"
    assert null_row["quality"] == "null"
    assert (
        replace(measurement, source_type=SourceType.OPCUA).source_quality
        == MeasurementSourceQuality.GOOD
    )
    assert (
        replace(measurement, source_type=SourceType.OPCUA, status_good=False).source_quality
        == MeasurementSourceQuality.NON_GOOD
    )


def test_range_summary_does_not_claim_truncated_points_cover_the_request():
    from industrial_phm.application.measurement_history import MeasurementHistoryPage
    from industrial_phm.presentation.measurement_history import measurement_history_range_summary

    measurement = HistoricalMeasurement(
        raw_evidence_id="raw",
        source_id="source",
        source_type=SourceType.OPCUA,
        asset_id="asset",
        channel_id="power",
        event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
        # A reader may return storage time in its local zone; display stays on UTC.
        event_at=(NOW - timedelta(minutes=1)).astimezone(timezone(timedelta(hours=9))),
        value=1.0,
        status_good=True,
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    page = MeasurementHistoryPage((MeasurementHistoryPoint(measurement, False),), True, 1)
    start = NOW - timedelta(days=1)
    summary = measurement_history_range_summary(page, start_at=start, end_at=NOW)
    assert summary["requested_start_inclusive"] == start.isoformat()
    assert summary["returned_start"] == (NOW - timedelta(minutes=1)).isoformat()
    assert summary["returned_points"] == 1
    assert summary["truncated"] is True
    empty = measurement_history_range_summary(
        MeasurementHistoryPage((), False, 1), start_at=start, end_at=NOW
    )
    assert empty["returned_start"] is None
    assert empty["returned_end"] is None
    assert empty["returned_points"] == 0


def test_monitor_analysis_windows_are_clipped_to_visible_time_range() -> None:
    from industrial_phm.presentation.measurement_history import _render_evidence_windows

    calls: list[tuple[datetime, datetime, str]] = []

    class _Axis:
        def axvspan(self, start_at, end_at, **kwargs):
            calls.append((start_at, end_at, kwargs["label"]))

    _render_evidence_windows(
        _Axis(),
        (
            (
                NOW - timedelta(hours=2),
                NOW - timedelta(minutes=15),
                "phase unbalance",
            ),
        ),
        start_at=NOW - timedelta(hours=1),
        end_at=NOW,
    )

    assert calls == [
        (
            NOW - timedelta(hours=1),
            NOW - timedelta(minutes=15),
            "analysis evidence",
        )
    ]
