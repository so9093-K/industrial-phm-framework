from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_FEATURE_NAMES,
    align_electrical_samples,
    electrical_window_features,
    resolve_electrical_roles,
)

T0 = datetime(2026, 10, 12, tzinfo=UTC)
_MEANING = {
    **{f"{p}상전류": ("phase current", f"phase {p}", "A") for p in "RST"},
    **{f"{p}상전압": ("phase voltage", f"phase {p}", "V") for p in "RST"},
    "주파수": ("frequency", "three-phase supply voltage", "Hz"),
    "전류평균": ("phase current", "three-phase", "A"),
}


def _observations(
    rows: list[dict[str, float | None]], *, good: bool = True
) -> list[ChannelObservation]:
    out = []
    for minute, row in enumerate(rows):
        for channel, value in row.items():
            prop, scope, unit = _MEANING[channel]
            out.append(
                ChannelObservation(
                    source_id="replay",
                    measurement_point_id=None,
                    channel_id=channel,
                    event_at=T0 + timedelta(minutes=minute),
                    value=value,
                    conflicting=False,
                    source_quality_good=good,
                    observed_property=prop,
                    scope=scope,
                    unit=unit,
                    semantic_version="aihub-239-semantics-v3",
                )
            )
    return out


def _row(
    current: float, voltage: float = 220.0, *, r_scale: float = 1.0
) -> dict[str, float | None]:
    return {
        "R상전류": current * r_scale,
        "S상전류": current,
        "T상전류": current,
        "R상전압": voltage,
        "S상전압": voltage,
        "T상전압": voltage,
        "주파수": 59.9,
        "전류평균": current,
    }


def test_roles_come_from_meaning_and_three_phase_mean_is_not_a_phase() -> None:
    roles, reason = resolve_electrical_roles(_observations([_row(10.0)]))
    assert reason is None and roles is not None
    assert roles.current == ("R상전류", "S상전류", "T상전류")
    assert roles.frequency == "주파수"


def test_missing_meaning_is_reported_instead_of_guessing_from_names() -> None:
    observations = [o for o in _observations([_row(10.0)]) if o.channel_id != "T상전압"]
    roles, reason = resolve_electrical_roles(observations)
    assert roles is None and reason is not None and "voltage T" in reason


def test_window_features_use_running_samples_only() -> None:
    rows = [_row(10.0), _row(10.0, r_scale=1.3), _row(0.2), _row(10.0), _row(10.0)]
    observations = _observations(rows)
    roles, _ = resolve_electrical_roles(observations)
    assert roles is not None
    samples, excluded = align_electrical_samples(observations, roles)
    assert len(samples) == 5 and excluded == {}
    features, reason, running = electrical_window_features(samples)
    assert reason is None and running == 4 and features is not None
    assert tuple(features) == ELECTRICAL_WINDOW_FEATURE_NAMES
    assert features["current.phase_r.mean_a"] == pytest.approx((10 + 13 + 10 + 10) / 4)
    assert features["current.unbalance.mean_percent"] > 0
    assert features["voltage.unbalance.mean_percent"] == 0
    assert features["frequency.mean_hz"] == pytest.approx(59.9)


def test_stopped_window_is_not_evaluated() -> None:
    observations = _observations([_row(0.1)] * 5)
    roles, _ = resolve_electrical_roles(observations)
    assert roles is not None
    samples, _ = align_electrical_samples(observations, roles)
    features, reason, running = electrical_window_features(samples)
    assert features is None and running == 0 and reason is not None and "not evaluated" in reason


def test_incomplete_and_bad_quality_times_are_counted_out() -> None:
    rows = [_row(10.0), {**_row(10.0), "주파수": None}, _row(10.0)]
    observations = _observations(rows)
    observations = [o for o in observations if not (o.channel_id == "S상전류" and o.event_at == T0)]
    roles, _ = resolve_electrical_roles(observations)
    assert roles is not None
    samples, excluded = align_electrical_samples(observations, roles)
    assert len(samples) == 1
    assert excluded == {"incomplete": 1, "missing-value": 1}
    bad = _observations([_row(10.0)], good=False)
    assert align_electrical_samples(bad, roles)[1] == {"non-good-quality": 1}


@pytest.mark.parametrize(
    "change",
    [
        {"measurement_point_id": "other-board"},
        {"source_id": "other-source"},
        {"semantic_version": "changed-v4"},
        {"unit": "mA"},
    ],
)
def test_mixed_streams_or_changed_meaning_cannot_supply_one_feature_vector(change) -> None:
    observations = _observations([_row(10.0)] * 3)
    observations[-1] = replace(observations[-1], **change)
    roles, reason = resolve_electrical_roles(observations)
    assert roles is None and reason is not None
