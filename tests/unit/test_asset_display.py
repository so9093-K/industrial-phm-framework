from dataclasses import replace
from datetime import UTC, datetime

import pytest

from industrial_phm.application import OpcUaSourceConfig, RegisteredSource
from industrial_phm.application.asset_display import resolve_asset_display_names
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.presentation.operations_shell import render_asset_title_html

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


def test_title_keeps_the_asset_id_under_the_display_name() -> None:
    names = resolve_asset_display_names((_source("a1", "compressor-1338", "공기압축기"),))

    named = render_asset_title_html("compressor-1338", names)
    assert '<h2 class="phm-asset-title">공기압축기</h2>' in named
    assert '<div class="phm-asset-id">compressor-1338</div>' in named
    assert render_asset_title_html("boiler-2297", names) == (
        '<h2 class="phm-asset-title">boiler-2297</h2>'
    )


@pytest.mark.parametrize("value", ["", " padded", "a" * 121, "tab\there"])
def test_display_name_rejects_values_that_cannot_be_a_label(value: str) -> None:
    source = _source("a1", "compressor-1338", None)
    with pytest.raises(ValueError, match="asset_display_name"):
        replace(source.config, asset_display_name=value)
