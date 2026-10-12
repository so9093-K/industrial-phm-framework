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
