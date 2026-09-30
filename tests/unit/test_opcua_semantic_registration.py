import pytest

from industrial_phm.application import (
    MeasurementDefinition,
    OPCUA_SEMANTIC_BINDING_INPUT_COLUMNS,
    parse_opcua_semantic_bindings,
)


def test_parse_opcua_semantic_bindings_preserves_explicit_meaning() -> None:
    (binding,) = parse_opcua_semantic_bindings(
        'Voltage_L1,phase voltage,phase R,,V,"meter data sheet, rev 2",site-v1,'
        '"commissioning map, panel A"',
        source_id="field-opcua",
    )

    assert binding.source_id == "field-opcua"
    assert binding.channel_id == "Voltage_L1"
    assert binding.version == "site-v1"
    assert binding.definition == MeasurementDefinition(
        observed_property="phase voltage",
        scope="phase R",
        unit="V",
        unit_evidence="meter data sheet, rev 2",
    )
    assert binding.interpretation_evidence == "commissioning map, panel A"


def test_parse_opcua_semantic_bindings_leaves_omitted_meaning_unresolved() -> None:
    (binding,) = parse_opcua_semantic_bindings(
        "Voltage_L1,,,,,,site-v1,explicitly unresolved during commissioning",
        source_id="field-opcua",
    )

    assert binding.channel_id == "Voltage_L1"
    assert binding.definition == MeasurementDefinition()


def test_parse_opcua_semantic_bindings_empty_input_creates_no_binding() -> None:
    assert parse_opcua_semantic_bindings("\n  \n", source_id="field-opcua") == ()


def test_parse_opcua_semantic_bindings_rejects_duplicate_channel() -> None:
    row = "Voltage_L1,phase voltage,phase R,,V,spec,site-v1,map"

    with pytest.raises(ValueError, match="duplicated"):
        parse_opcua_semantic_bindings(f"{row}\n{row}", source_id="field-opcua")


def test_parse_opcua_semantic_bindings_rejects_wrong_column_count() -> None:
    with pytest.raises(ValueError, match=str(len(OPCUA_SEMANTIC_BINDING_INPUT_COLUMNS))):
        parse_opcua_semantic_bindings(
            "Voltage_L1,phase voltage,phase R,V",
            source_id="field-opcua",
        )


def test_parse_opcua_semantic_bindings_requires_unit_evidence_with_known_unit() -> None:
    with pytest.raises(ValueError, match="known units require evidence"):
        parse_opcua_semantic_bindings(
            "Voltage_L1,phase voltage,phase R,,V,,site-v1,map",
            source_id="field-opcua",
        )
