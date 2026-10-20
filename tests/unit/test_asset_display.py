from dataclasses import replace
from datetime import UTC, datetime

import pytest

from industrial_phm.application import (
    ChannelLabel,
    FileSourceConfig,
    OpcUaSourceConfig,
    RegisteredSource,
)
from industrial_phm.application.asset_display import (
    resolve_asset_display_names,
    resolve_channel_labels,
)
from industrial_phm.connectors import OpcUaNodeMapping

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


def _source(source_id: str, asset_id: str, name: str | None) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=source_id,
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            asset_id=asset_id,
            node_mappings=(OpcUaNodeMapping("current", "ns=2;s=current"),),
            asset_display_name=name,
        ),
        registered_at=NOW,
    )


def test_display_name_is_used_only_when_declaring_sources_agree() -> None:
    names = resolve_asset_display_names(
        (
            _source("a1", "compressor-1338", "공기압축기 · reference asset"),
            _source("a2", "compressor-1338", None),
            _source("a3", "compressor-1338", "공기압축기 · reference asset"),
            _source("b1", "pump-7", "Pump A"),
            _source("b2", "pump-7", "Pump B"),
            _source("c1", "boiler-2297", None),
        )
    )

    assert names.label("compressor-1338") == "공기압축기 · reference asset"
    assert names.option_label("compressor-1338") == "공기압축기 · reference asset · compressor-1338"
    # Disagreement is not resolved by guessing; the stable ID is shown and reported.
    assert names.label("pump-7") == "pump-7"
    assert names.conflicts == {"pump-7": ("Pump A", "Pump B")}
    assert names.label("boiler-2297") == "boiler-2297"
    assert names.option_label("boiler-2297") == "boiler-2297"


@pytest.mark.parametrize("value", ["", " padded", "a" * 121, "tab\there"])
def test_display_name_rejects_values_that_cannot_be_a_label(value: str) -> None:
    source = _source("a1", "compressor-1338", None)
    with pytest.raises(ValueError, match="asset_display_name"):
        replace(source.config, asset_display_name=value)


def _csv(source_id: str, asset_id: str, labels: tuple[ChannelLabel, ...]) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=source_id,
        config=FileSourceConfig(
            source_path="/data/pump.csv",
            asset_id=asset_id,
            channel_columns=("current_a", "temperature_c"),
            timestamp_column="timestamp",
            channel_labels=labels,
        ),
        registered_at=NOW,
    )


def test_channel_labels_are_shown_only_where_the_asset_sources_agree() -> None:
    current = ChannelLabel("current_a", "모터 전류", "A")
    labels = resolve_channel_labels(
        (
            _csv("f1", "pump-7", (current, ChannelLabel("temperature_c", "베어링 온도", "°C"))),
            _csv("f2", "pump-7", (current, ChannelLabel("temperature_c", "케이싱 온도", "°C"))),
            _csv("f3", "pump-8", (ChannelLabel("current_a", "다른 설비 전류"),)),
        ),
        "pump-7",
    )
    # A label names a channel; two sources disagreeing leaves the channel ID on screen.
    assert labels == {"current_a": ("모터 전류", "A")}


def test_a_channel_label_must_name_a_registered_channel_once() -> None:
    with pytest.raises(ValueError, match="registered channels once"):
        _csv("f1", "pump-7", (ChannelLabel("voltage", "전압"),))
    with pytest.raises(ValueError, match="channel label"):
        ChannelLabel("current_a", "x" * 61)
