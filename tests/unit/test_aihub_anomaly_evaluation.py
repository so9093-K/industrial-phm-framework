from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from types import SimpleNamespace

import pytest

from industrial_phm.application.electrical_window_features import ElectricalWindowSample
from industrial_phm.experiments import aihub_electrical_anomaly as ev

T0 = datetime(2020, 11, 1, tzinfo=UTC)


def test_injection_plan_preserves_coverage_and_six_hour_gaps_across_types() -> None:
    rows = [ev.WindowRow(T0 + i * ev.WINDOW, {"x": 1.0}, None) for i in range(20 * 288)]
    reserved = []
    rng = random.Random(239)
    for injection in sorted(ev.INJECTIONS, key=lambda i: i.duration, reverse=True):
        starts = ev.injection_starts(rows, rng, 3, injection.duration, reserved=reserved)
        assert len(starts) == 3
        reserved.extend((at, injection.duration) for at in starts)
    ordered = sorted(reserved)
    for (at, duration), (next_at, _) in pairwise(ordered):
        assert next_at - (at + duration) >= timedelta(hours=6)


def test_short_coverage_is_reported_as_missing_injection_positions() -> None:
    rows = [ev.WindowRow(T0 + i * ev.WINDOW, {"x": 1.0}, None) for i in range(6)]
    assert ev.injection_starts(rows, random.Random(239), 3, timedelta(minutes=30)) == [T0]


class _FrequencyPackage:
    manifest = SimpleNamespace(output=SimpleNamespace(threshold=0.5))

    def evaluate(self, rows):
        return tuple(row[-1] - 60 for row in rows)


def test_injection_uses_entire_prior_interval_state_instead_of_resetting_a_neighborhood() -> None:
    samples = tuple(
        ElectricalWindowSample(
            at=T0 + timedelta(minutes=i),
            current=(10.0,) * 3 if i < 10 or i >= 120 else (0.0,) * 3,
            voltage=(220.0,) * 3,
            frequency=61.0 if i < 10 else 60.0,
        )
        for i in range(150)
    )
    result = ev.evaluate_injection(
        _FrequencyPackage(), samples, ev.INJECTIONS[3], T0 + timedelta(hours=2), 0
    )
    assert result["masked_by_existing_interval"]
    assert not result["detected"]


def test_reference_asset_and_six_development_members_are_mandatory() -> None:
    with pytest.raises(ValueError, match="six fixed"):
        ev.choose_development_members(["a", "b"], "missing-reference")


def test_time_split_never_shares_a_window_across_fit_and_holdout() -> None:
    samples = tuple(
        ElectricalWindowSample(T0 + timedelta(minutes=i), (10.0,) * 3, (220.0,) * 3, 60.0)
        for i in range(100)
    )
    train, holdout, boundary = ev.split_device(samples)
    assert {w.start for w in ev.window_rows(train)}.isdisjoint(
        w.start for w in ev.window_rows(holdout)
    )
    assert train[-1].at < boundary <= holdout[0].at
