import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    ChannelSemanticBinding,
    MeasurementDefinition,
    OpcUaSourceConfig,
    RegisteredSource,
)
from industrial_phm.application.measurement_history import (
    MultiSignalMeasurementHistoryAggregation,
    MultiSignalMeasurementHistoryBucket,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.presentation.monitor_workspace import (
    chart_payload,
    comparison_channels,
    signal_payload,
)

AT = datetime(2026, 10, 6, tzinfo=UTC)


def bucket(channel="r", unit="A", source="source", point="panel"):
    return MultiSignalMeasurementHistoryBucket(
        channel_id=channel,
        source_id=source,
        source_type="opcua",
        measurement_point_id=point,
        bucket_start=AT,
        bucket_end=AT + timedelta(minutes=1),
        first_event_at=AT,
        last_event_at=AT,
        observation_count=3,
        usable_count=1,
        null_count=1,
        non_good_count=1,
        conflict_count=0,
        minimum=100,
        maximum=100,
        mean=100,
        interpretation_json=json.dumps(
            {"semantics": {"definition": {"observed_property": "phase current", "unit": unit}}}
        ),
    )


def result(*buckets):
    return MultiSignalMeasurementHistoryAggregation(
        start_at=AT,
        end_at=AT + timedelta(minutes=1),
        bucket_seconds=60,
        snapshot_id=42,
        buckets=buckets,
    )


def test_related_series_share_a_unit_axis_and_keep_quality_evidence():
    payload = chart_payload(result(bucket("r"), bucket("s")), ["s", "r"])
    assert payload["snapshot_id"] == 42
    assert len(payload["groups"]) == 1
    s, r = payload["groups"][0]["series"]
    assert (s["channel"], r["channel"]) == ("s", "r")
    assert s["color"] != r["color"]
    assert s["buckets"][0]["mean"] == 100
    assert s["buckets"][0]["usable"] == 1
    assert s["buckets"][0]["null"] == s["buckets"][0]["non_good"] == 1


def test_units_sources_and_measurement_points_never_collapse_into_one_axis():
    payload = chart_payload(
        result(
            bucket("r"),
            bucket("v", "V"),
            bucket("other", source="another"),
            bucket("other-point", point="another"),
            bucket("unknown", None),
        )
    )
    assert len(payload["groups"]) == 5
    assert {group["unit"] for group in payload["groups"]} == {"A", "V", "unit unknown"}
    assert all(group["series"][0]["buckets"][0]["mean"] == 100 for group in payload["groups"])


def test_a_channel_with_changed_interpretation_is_split_instead_of_relabelled():
    payload = chart_payload(result(bucket("r", "A"), bucket("r", "V")))
    assert len(payload["groups"]) == 2
    assert {group["unit"] for group in payload["groups"]} == {"A", "V"}
    # No usable value is manufactured when a bucket contains only excluded evidence.
    unusable = replace(bucket("r"), usable_count=0, mean=None, minimum=None, maximum=None)
    assert chart_payload(result(unusable))["groups"][0]["series"][0]["buckets"][0]["mean"] is None


def test_registration_fills_unobserved_slots_without_reinterpreting_stored_data():
    binding = ChannelSemanticBinding(
        source_id="source",
        channel_id="r",
        version="new-map",
        definition=MeasurementDefinition(
            observed_property="phase current", unit="A", unit_evidence="manual"
        ),
        interpretation_evidence="mapping",
    )
    source = RegisteredSource(
        source_id="source",
        name="Panel",
        registered_at=AT,
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            asset_id="asset",
            measurement_point_id="panel",
            node_mappings=(OpcUaNodeMapping("r", "ns=2;s=r"), OpcUaNodeMapping("s", "ns=2;s=s")),
            semantic_bindings=(binding,),
        ),
    )
    stored = {
        "channel": "r",
        "source": "source",
        "measurement_point": "panel",
        "value": 100,
        "unit": "unknown",
        "observed_property": "unresolved",
        "time": AT.isoformat(),
    }
    rows = signal_payload([stored], [source], "asset")
    r, s = rows
    assert r["unit"] == "unknown" and r["observed_property"] == "unresolved"
    assert r["time"] == AT.isoformat()
    assert s["value"] is None and s["time"] is None and s["source_quality"] == "unknown"
    empty = signal_payload([], [source], "asset")
    assert empty[0]["unit"] == "A" and empty[0]["value"] is None
    assert empty[0]["quality"] == "not yet observed"


def test_default_comparisons_require_declared_compatible_meaning():
    base = {
        "observed_property": "phase current",
        "unit": "A",
        "source": "source",
        "measurement_point": "panel",
    }
    rows = [
        {**base, "channel": "r"},
        {**base, "channel": "s"},
        {**base, "channel": "another", "source": "another"},
    ]
    assert comparison_channels(rows, "r", None) == ("s",)
    assert comparison_channels(rows, "r", ["s", "s", "missing", "r"]) == ("s",)
    assert comparison_channels([{**row, "unit": "unknown"} for row in rows], "r", None) == ()


def test_never_observed_registered_comparisons_are_not_dropped():
    rows = [
        {
            "channel": name,
            "unit": "A",
            "observed_property": "phase current",
            "source": "source",
            "measurement_point": "panel",
            "value": None,
        }
        for name in ("r", "s", "t")
    ]
    assert comparison_channels(rows, "r", ["s", "t"]) == ("s", "t")
    assert comparison_channels(rows, "r", None) == ("s", "t")


def test_chart_origins_and_interpretation_versions_remain_visible():
    original = bucket("r", source="alpha")
    newer = replace(
        bucket("r", source="beta"),
        interpretation_json=json.dumps(
            {
                "semantics": {
                    "version": "site-v2",
                    "definition": {"observed_property": "phase current", "unit": "A"},
                }
            }
        ),
    )
    groups = chart_payload(result(original, newer))["groups"]
    assert len(groups) == 2
    assert groups[0]["origin"] == "alpha / panel"
    assert groups[1]["origin"] == "beta / panel"
    assert groups[1]["interpretation"] == "site-v2"
