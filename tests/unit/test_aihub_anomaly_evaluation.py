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
    manifest = SimpleNamespace(output=SimpleNamespace(threshold=0.4))

    def evaluate(self, rows):
        return tuple(row[-1] - 60 for row in rows)


def test_injection_after_long_unobserved_gap_does_not_claim_prior_interval_continuity() -> None:
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
    assert not result["masked_by_existing_interval"]
    assert result["detected"]


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


def test_fit_failure_remains_in_evaluation_population_and_all_case_denominators(
    monkeypatch,
) -> None:
    from tools.phm.evaluate_aihub_anomaly import _evaluate_member, _rates

    samples = tuple(
        ElectricalWindowSample(T0 + timedelta(minutes=i), (10.0,) * 3, (0.0,) * 3, 60.0)
        for i in range(100)
    )
    device = ev.DeviceRecord("member", "1338", samples, None, {}, "a" * 64)
    monkeypatch.setattr(ev, "load_device", lambda *args, **kwargs: device)
    monkeypatch.setattr(ev, "MIN_TRAIN_RUNNING", 1)
    monkeypatch.setattr(ev, "MIN_HOLDOUT_RUNNING", 1)
    report = _evaluate_member(("unused", "a" * 64, "member", ("pca-residual",), "0" * 40))
    assert report["eligible"]
    candidate = report["candidates"]["pca-residual"]
    assert "fit unavailable" in candidate["error"]
    assert len(candidate["injections"]) == 15
    assert all(not i["detected"] for i in candidate["injections"])
    summary = _rates([report], "pca-residual")
    assert summary["devices"] == 1 and summary["alarm_evaluated_devices"] == 0
    assert summary["fit_failed_devices"] == 1
    assert summary["holdout_alarm_fraction"] is None
    assert all(rate == 0 for rate in summary["detection_rate"].values())
