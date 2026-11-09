"""Operating-change analysis must keep reference, physical meaning and missingness honest."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import sin

import pytest

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.electrical_condition import (
    ElectricalSample,
    analyze_electrical_condition,
    electrical_samples,
)
from industrial_phm.application.operating_state import OperatingLevels

AT = datetime(2026, 10, 12, tzinfo=UTC)
CHANNELS = ("vR", "vS", "vT", "iR", "iS", "iT")


def _samples(start: datetime, *, current: float, count: int = 120) -> tuple[ElectricalSample, ...]:
    return tuple(
        ElectricalSample(
            start + timedelta(minutes=index),
            (230 + sin(index), 231 + sin(index * 0.4), 229 + sin(index * 0.7)),
            (current + sin(index), current + 1 + sin(index * 0.4), current + 2 + sin(index * 0.7)),
        )
        for index in range(count)
    )


def _analyze(reference, target):
    return analyze_electrical_condition(
        reference,
        target,
        channels=CHANNELS,
        include_voltage=True,
        include_current=True,
        reference_start=AT,
        target_start=AT + timedelta(hours=2),
        target_end=AT + timedelta(hours=4),
    )


def test_load_change_is_explained_and_target_cannot_change_reference_calibration() -> None:
    reference = _samples(AT, current=10)
    same = _analyze(reference, _samples(AT + timedelta(hours=2), current=10))
    changed = _analyze(reference, _samples(AT + timedelta(hours=2), current=80))
    assert changed["reference"] == same["reference"]
    assert changed["pattern"]["threshold"] == same["pattern"]["threshold"]
    assert changed["target"]["current_mean_a"] > same["target"]["current_mean_a"] + 60
    assert changed["pattern"]["above_reference_count"] > same["pattern"]["above_reference_count"]
    assert changed["pattern"]["reference_samples"] == 120
    assert changed["pattern"]["scored_samples"] == 120
    assert all(row["at"].startswith("2026-10-12T0") for row in changed["timeline"])


def test_each_operating_level_is_compared_only_with_the_same_level() -> None:
    levels = OperatingLevels((1.0, 45.0), (30.0, 60.0))
    reference = _samples(AT, current=60)
    # Half the target runs near 30 A, a level the reference never ran at; the rest near 60 A,
    # with a voltage dip at one 60 A minute.
    target = list(_samples(AT + timedelta(hours=2), current=30, count=60))
    target += _samples(AT + timedelta(hours=3), current=60, count=60)
    dip = target[90]
    target[90] = replace(dip, voltage=(180.0, 181.0, 179.0))
    whole = _analyze(reference, target)["pattern"]
    split = analyze_electrical_condition(
        reference,
        target,
        channels=CHANNELS,
        include_voltage=True,
        include_current=True,
        reference_start=AT,
        target_start=AT + timedelta(hours=2),
        target_end=AT + timedelta(hours=4),
        levels=levels,
    )["pattern"]
    # One model over everything calls the whole 30 A half a departure from the reference.
    assert whole["above_reference_count"] >= 60
    # By level, the 30 A minutes have nothing to be compared with and are counted apart.
    assert split["split"] == "operating-level" and split["threshold"] == 1.0
    assert split["scored_samples"] == 60 and split["unscored_samples"] == 60
    by_band = {part["band"]: part for part in split["levels"]}
    assert by_band[1]["reference_samples"] == 0 and by_band[1]["target_samples"] == 60
    assert by_band[1]["state"] == "insufficient-reference"
    assert by_band[2]["state"] == "scored" and by_band[2]["reference_samples"] == 120
    # The dip at 60 A is still found, first, with its level.
    first = split["notable"][0]
    assert first["at"] == dip.at.isoformat() and first["band"] == 2 and first["score"] > 1
    assert split["above_reference_count"] < 10


def test_zero_current_is_low_signal_not_zero_imbalance_or_healthy() -> None:
    target = tuple(
        ElectricalSample(AT + timedelta(hours=2, minutes=i), (230, 230, 230), (0, 0, 0))
        for i in range(60)
    )
    report = _analyze((), target)
    assert report["target"]["current_mean_a"] == 0
    assert report["target"]["current_unbalance_p95_percent"] is None
    assert report["target"]["current_low_signal_count"] == 60
    assert report["pattern"]["state"] == "insufficient-reference"
    assert all(row["current_unbalance_percent"] is None for row in report["timeline"])


def test_missing_minutes_do_not_turn_into_observed_operating_hours() -> None:
    target = tuple(
        ElectricalSample(AT + timedelta(hours=2, minutes=i), (230, 230, 230), (10, 10, 10))
        for i in (0, 1, 11, 12)
    )
    report = _analyze((), target)
    assert report["target"]["current_observed_hours"] == pytest.approx(2 / 60)
    assert report["target"]["current_above_floor_hours"] == pytest.approx(2 / 60)


def test_alignment_rejects_bad_values_without_borrowing_another_measurement_point() -> None:
    observations = [
        ChannelObservation(
            "source",
            "point-a",
            f"v{phase}",
            AT,
            230,
            False,
            True,
            "phase voltage",
            f"phase {phase}",
            "V",
            "v1",
        )
        for phase in "RS"
    ]
    observations.append(
        ChannelObservation(
            "source", "point-b", "vT", AT, 230, False, True, "phase voltage", "phase T", "V", "v1"
        )
    )
    rows, excluded = electrical_samples(
        observations,
        source_id="source",
        point_id="point-a",
        voltage_channels=("vR", "vS", "vT"),
        current_channels=(),
    )
    assert rows[0].voltage is None
    assert excluded == {"missing-or-duplicate-phase": 1}


def test_reference_cannot_overlap_the_target_or_repeat_timestamps() -> None:
    with pytest.raises(ValueError, match="reference contains"):
        _analyze(
            _samples(AT + timedelta(hours=2), current=10),
            _samples(AT + timedelta(hours=2), current=20),
        )
    with pytest.raises(ValueError, match="unique increasing"):
        reference = _samples(AT, current=10)
        _analyze((reference[0], reference[0]), _samples(AT + timedelta(hours=2), current=20))


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"value": None}, "missing-value"),
        ({"source_quality_good": False}, "conflict-or-bad-quality"),
        ({"conflicting": True}, "conflict-or-bad-quality"),
        ({"unit": "kV"}, "unconfirmed-meaning"),
        ({"value": -1.0}, "invalid-electrical-value"),
    ],
)
def test_unusable_phase_cannot_produce_a_balanced_or_normal_result(change, reason) -> None:
    observations = [
        ChannelObservation(
            "source",
            "meter",
            f"v{phase}",
            AT,
            230,
            False,
            True,
            "phase voltage",
            f"phase {phase}",
            "V",
            "v1",
        )
        for phase in "RST"
    ]
    observations[0] = replace(observations[0], **change)
    rows, excluded = electrical_samples(
        observations,
        source_id="source",
        point_id="meter",
        voltage_channels=("vR", "vS", "vT"),
        current_channels=(),
    )
    assert rows[0].voltage is None
    assert excluded == {reason: 1}
