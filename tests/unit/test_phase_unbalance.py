from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.measurement_semantics import ChannelSemanticCandidate
from industrial_phm.application.phase_unbalance import (
    ChannelObservation,
    ChannelSelection,
    PhaseUnbalanceConfig,
    resolve_phase_channels,
    run_phase_unbalance_analysis,
    unbalance_percent,
)

T0 = datetime(2021, 1, 1, tzinfo=UTC)


def _obs(channel, minute, value, *, prop=None, unit=None, conflicting=False, point=None):
    phase = channel[0]
    quantity = "phase voltage" if "전압" in channel else "phase current"
    return ChannelObservation(
        source_id="s",
        measurement_point_id=point,
        channel_id=channel,
        event_at=T0 + timedelta(minutes=minute),
        value=value,
        conflicting=conflicting,
        source_quality_good=True,
        observed_property=prop or quantity,
        scope=f"phase {phase}",
        unit=unit or ("V" if "전압" in channel else "A"),
        semantic_version="aihub-239-semantics-v2",
    )


class _Reader:
    def __init__(self, observations):
        self.observations = observations

    def current_snapshot_id(self):
        return 7

    def list_channel_semantics(self, asset_id, **kwargs):
        assert kwargs["snapshot_id"] == 7
        counts = Counter(
            (o.measurement_point_id, o.channel_id, o.observed_property, o.scope, o.unit)
            for o in self.observations
            if o.observed_property is not None
        )
        return tuple(
            ChannelSemanticCandidate(point, channel, prop, scope, unit, "v", count)
            for (point, channel, prop, scope, unit), count in counts.items()
        )

    def query_channel_observations(self, asset_id, **kwargs):
        assert kwargs["snapshot_id"] == 7
        return tuple(o for o in self.observations if o.channel_id in kwargs["channel_ids"])


def test_unbalance_uses_only_confirmed_complete_samples_and_counts_exclusions():
    assert unbalance_percent([220, 230, 225]) == pytest.approx(5 / 225 * 100)
    volts = ("R상전압", "S상전압", "T상전압")
    amps = ("R상전류", "S상전류", "T상전류")
    observations = [
        *(_obs(c, 0, v) for c, v in zip(volts, (220, 230, 225), strict=True)),
        *(_obs(c, 0, v) for c, v in zip(amps, (10, 10, 13), strict=True)),
        # A phase bound to an unconfirmed meaning is not eligible input.
        *(_obs(c, 1, 220, prop=None if c[0] != "R" else "unresolved") for c in volts),
        *(_obs(c, 1, v) for c, v in zip(amps, (0.1, 0.2, 0.1), strict=True)),
        *(_obs(c, 2, 220) for c in volts[:2]),
        _obs("R상전류", 2, 5, conflicting=True),
        _obs("S상전류", 2, 5),
        _obs("T상전류", 2, 5),
    ]
    analysis = run_phase_unbalance_analysis(
        _Reader(observations),
        asset_id="a",
        source_id="s",
        start_at=T0,
        end_at=T0 + timedelta(hours=1),
    )
    voltage, current = analysis.evidence.results
    assert voltage.evaluated_samples == 1
    assert voltage.median_percent == pytest.approx(2.2222, abs=1e-4)
    assert voltage.excluded_samples == {"unconfirmed-semantics": 1, "incomplete-phases": 1}
    assert current.evaluated_samples == 1
    assert current.max_percent == pytest.approx(2 / 11 * 100)
    assert current.excluded_samples == {"low-signal": 1, "conflicting-value": 1}
    assert analysis.evidence.input_reference.snapshot_id == 7
    assert analysis.run.data_quality.state.value == "warning"
    assert analysis.run.data_quality.issue_codes == ("excluded-current-conflicting-value",)

    with pytest.raises(ValueError, match="no eligible"):
        run_phase_unbalance_analysis(
            _Reader(observations[6:]),
            asset_id="a",
            source_id="s",
            start_at=T0 + timedelta(minutes=1),
            end_at=T0 + timedelta(hours=1),
        )


def test_p95_stays_inside_observed_range_for_two_samples():
    volts = ("R상전압", "S상전압", "T상전압")
    amps = ("R상전류", "S상전류", "T상전류")
    observations = [
        *(_obs(c, 0, v) for c, v in zip(volts, (220, 225, 230), strict=True)),
        *(_obs(c, 1, v) for c, v in zip(volts, (200, 225, 250), strict=True)),
        *(_obs(c, 0, v) for c, v in zip(amps, (10, 10, 13), strict=True)),
        *(_obs(c, 1, v) for c, v in zip(amps, (10, 10, 20), strict=True)),
    ]

    analysis = run_phase_unbalance_analysis(
        _Reader(observations),
        asset_id="a",
        source_id="s",
        start_at=T0,
        end_at=T0 + timedelta(hours=1),
    )

    for series in analysis.evidence.results:
        assert series.median_percent <= series.p95_percent <= series.max_percent


def test_multiple_measurement_points_require_explicit_selection():
    volts = ("R상전압", "S상전압", "T상전압")
    amps = ("R상전류", "S상전류", "T상전류")
    observations = [
        *(_obs(c, 0, v, point="p1") for c, v in zip(volts, (220, 225, 230), strict=True)),
        *(_obs(c, 0, v, point="p1") for c, v in zip(amps, (10, 10, 13), strict=True)),
        *(_obs(c, 0, v, point="p2") for c, v in zip(volts, (210, 215, 220), strict=True)),
        *(_obs(c, 0, v, point="p2") for c, v in zip(amps, (8, 9, 10), strict=True)),
    ]

    with pytest.raises(ValueError, match="multiple measurement points"):
        run_phase_unbalance_analysis(
            _Reader(observations),
            asset_id="a",
            source_id="s",
            start_at=T0,
            end_at=T0 + timedelta(hours=1),
        )

    selected = run_phase_unbalance_analysis(
        _Reader(observations),
        asset_id="a",
        source_id="s",
        start_at=T0,
        end_at=T0 + timedelta(hours=1),
        measurement_point_id="p1",
    )
    assert selected.run.measurement_point_id == "p1"
    assert selected.evidence.input_reference.measurement_point_id == "p1"


def _candidate(channel, prop, phase, unit):
    return ChannelSemanticCandidate(None, channel, prop, f"phase {phase}", unit, "site-v1", 1)


def test_channels_are_chosen_by_bound_meaning_not_source_names():
    site = [
        _candidate("Voltage_L1", "phase voltage", "R", "V"),
        _candidate("Voltage_L2", "phase voltage", "S", "V"),
        _candidate("Voltage_L3", "phase voltage", "T", "V"),
        _candidate("Current_L1", "phase current", "R", "A"),
        # Current L2/L3 carry no binding here, so current stays unresolved.
        _candidate("Voltage_avg", "phase voltage", "three-phase", "V"),
    ]
    resolved = resolve_phase_channels(site)
    assert resolved == {
        "voltage": ("Voltage_L1", "Voltage_L2", "Voltage_L3"),
        "current": None,
    }
    with pytest.raises(ValueError, match="ambiguous phase channel roles"):
        resolve_phase_channels([*site, _candidate("Spare_L1", "phase voltage", "R", "V")])

    observations = [
        ChannelObservation(
            "s", None, channel, T0, value, False, True, "phase voltage", f"phase {phase}", "V", "v"
        )
        for channel, phase, value in (
            ("Voltage_L1", "R", 220.0),
            ("Voltage_L2", "S", 230.0),
            ("Voltage_L3", "T", 225.0),
        )
    ]
    analysis = run_phase_unbalance_analysis(
        _Reader(observations), asset_id="a", source_id="s", start_at=T0, end_at=T0 + timedelta(1)
    )
    voltage, current = analysis.evidence.results
    assert voltage.channels == ("Voltage_L1", "Voltage_L2", "Voltage_L3")
    assert voltage.channel_selection == ChannelSelection.SEMANTIC_ROLE
    assert voltage.evaluated_samples == 1
    assert current.channel_selection == ChannelSelection.UNRESOLVED
    # The recorded configuration names the channels used, for exact recomputation.
    assert analysis.evidence.config == PhaseUnbalanceConfig(
        voltage_channels=("Voltage_L1", "Voltage_L2", "Voltage_L3")
    )
