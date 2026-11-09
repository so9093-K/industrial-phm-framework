from __future__ import annotations

import json

import numpy as np
import pytest

from industrial_phm.application.operating_state import (
    STOPPED_BELOW_A,
    find_levels,
    histogram_edges,
    main_current,
    running_bins,
)


def _levels(values: np.ndarray) -> tuple[list[float], list[float], list[float]]:
    """Levels of raw currents, binned the way the history counts them."""
    low, width, bins = running_bins(
        float(values.min()), float(values.max()), int((values >= STOPPED_BELOW_A).sum())
    )
    edges = histogram_edges(low, width, bins)
    counts = np.bincount(np.searchsorted(edges, values, side="right"), minlength=len(edges) + 1)
    found = find_levels(low, width, counts[1:])
    bands = np.searchsorted(found.edges, values, side="right")
    shares = np.bincount(bands, minlength=len(found.edges) + 1) / values.size
    return list(found.edges), list(found.typical), list(shares)


def test_each_running_peak_is_a_level_and_a_stop_is_apart() -> None:
    rng = np.random.default_rng(0)
    currents = np.concatenate([np.zeros(2000), rng.normal(20, 3, 3000), rng.normal(65, 2, 5000)])
    edges, typical, shares = _levels(currents)
    assert edges[0] == STOPPED_BELOW_A and 30 < edges[1] < 50
    assert typical == [pytest.approx(20, abs=1.5), pytest.approx(65, abs=1.5)]
    assert shares == [pytest.approx(0.2), pytest.approx(0.3), pytest.approx(0.5)]


def test_a_rare_bump_joins_its_neighbour() -> None:
    rng = np.random.default_rng(1)
    # 2 % of the time near 50 A, between levels at 30 A and 62 A.
    currents = np.concatenate(
        [rng.normal(30, 1, 3000), rng.normal(50, 0.5, 140), rng.normal(62, 1.5, 3800)]
    )
    edges, typical, _ = _levels(currents)
    assert len(typical) == 2
    assert 30 < edges[1] < 50


@pytest.mark.parametrize(
    "currents",
    [
        np.random.default_rng(2).normal(40, 1, 5000),  # one level
        np.random.default_rng(3).uniform(5, 60, 5000),  # no peak stands out
        np.full(100, 12.0),  # one value
        np.random.default_rng(4).normal(40, 1, 20),  # too few values to split
    ],
)
def test_without_separate_peaks_running_is_one_level(currents: np.ndarray) -> None:
    edges, typical, _ = _levels(currents)
    assert edges == [STOPPED_BELOW_A]
    assert len(typical) == 1


def test_a_record_that_never_ran_has_no_level() -> None:
    edges, typical, shares = _levels(np.zeros(500))
    assert (edges, typical, shares) == ([STOPPED_BELOW_A], [], [1.0, 0.0])


def _meaning(scope: str | None) -> str:
    definition = {"observed_property": "phase current", "scope": scope, "unit": "A"}
    return json.dumps({"semantics": {"definition": definition}})


def test_the_three_phase_current_shows_how_the_equipment_ran() -> None:
    signals = [
        ("voltage", "V", _meaning("three-phase")),
        ("r", "A", _meaning("phase R")),
        ("mean", "A", _meaning("three-phase")),
    ]
    assert main_current(signals) == "mean"
    assert main_current(signals[:2]) == "r"
    assert main_current(signals[:1]) is None
    # A current whose stored meaning is open but whose unit is shown as A still counts.
    assert main_current([("pf", None, "{}"), ("전류평균", "A", "{}")]) == "전류평균"
