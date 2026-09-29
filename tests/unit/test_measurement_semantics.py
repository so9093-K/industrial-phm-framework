from dataclasses import asdict

import pytest

from industrial_phm.application.measurement_semantics import MeasurementDefinition


def test_unresolved_property_is_not_a_raw_channel_label():
    assert asdict(MeasurementDefinition()) == {
        "observed_property": None,
        "scope": None,
        "statistic": None,
        "unit": None,
        "unit_evidence": None,
    }
    definition = MeasurementDefinition(
        observed_property="active_power", unit="kW", unit_evidence="manual"
    )
    assert definition.observed_property == "active_power"
    with pytest.raises(ValueError, match="evidence"):
        MeasurementDefinition(unit="kW")
    with pytest.raises(ValueError, match="empty"):
        MeasurementDefinition(observed_property=" ")


def test_aihub_dictionary_confirms_only_items_where_document_and_data_agree():
    from industrial_phm.adapters.aihub_power_history import confirmed_channel_definition

    frequency = confirmed_channel_definition("주파수")
    assert (frequency.observed_property, frequency.unit) == ("frequency", "Hz")
    assert confirmed_channel_definition("전류평균").statistic == (
        "arithmetic mean of phases R, S and T"
    )
    # Power, power factor and energy contradict their documented scale (and
    # power "평균" is a three-phase sum); temperature has no independent check.
    for channel in ("유효전력평균", "R상유효전력", "역률평균", "누적전력량", "온도"):
        assert confirmed_channel_definition(channel) == MeasurementDefinition()
