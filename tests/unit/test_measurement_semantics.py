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
