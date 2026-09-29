from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.alignment import (
    AlignmentPolicyKind,
    TemporalAlignmentPolicy,
    ValueOrigin,
    align_observations,
)
from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.phase_unbalance import (
    PhaseUnbalanceConfig,
    phase_unbalance_policy_digest,
    run_phase_unbalance_on_window,
)

T0 = datetime(2026, 9, 29, 12, tzinfo=UTC)
MS = timedelta(milliseconds=1)
BOUNDED = TemporalAlignmentPolicy(
    AlignmentPolicyKind.BOUNDED_PREVIOUS,
    max_age=50 * MS,
    basis="meter refreshes RMS values every 20 ms (test fixture)",
)


def _obs(channel, at_ms, value, *, conflicting=False):
    return ChannelObservation(
        "s", None, channel, T0 + at_ms * MS, value, conflicting, True, "p", None, None, None
    )


def test_strict_needs_every_channel_at_one_timestamp():
    result = align_observations(
        [_obs("a", 0, 1.0), _obs("b", 0, 2.0), _obs("a", 10, 3.0)], ("a", "b")
    )
    assert [s.aligned_at for s in result.samples] == [T0]
    assert result.excluded == {"incomplete-phases": 1}


def test_bounded_previous_carries_only_recent_earlier_values_and_keeps_provenance():
    observations = [
        _obs("a", 0, 1.0),
        _obs("b", 0, 2.0),
        _obs("a", 20, 3.0),  # b carried from 0 ms: 20 ms old
        _obs("a", 100, 4.0),  # b is 100 ms old: beyond max_age
        _obs("b", 130, 5.0),  # a carried from 100 ms; never b's future value at 100 ms
    ]
    result = align_observations(observations, ("a", "b"), BOUNDED)
    assert [s.aligned_at - T0 for s in result.samples] == [0 * MS, 20 * MS, 130 * MS]
    assert result.excluded == {"no-recent-phase-value": 1}
    carried = result.samples[1].values[1]
    assert (carried.origin, carried.age, carried.observation) == (
        ValueOrigin.CARRIED,
        20 * MS,
        observations[1],  # the original observation, timestamp untouched
    )
    assert result.samples[2].values[0].observation.value == 4.0
    assert result.samples[2].values[0].origin == ValueOrigin.CARRIED



def test_bounded_previous_uses_event_transition_clock_for_staggered_updates():
    observations = [
        _obs("a", 0, 1.0),
        _obs("b", 0, 2.0),
        _obs("c", 0, 3.0),
        _obs("a", 10, 10.0),
        _obs("b", 15, 20.0),
        _obs("c", 20, 30.0),
    ]
    result = align_observations(observations, ("a", "b", "c"), BOUNDED)

    assert [sample.aligned_at - T0 for sample in result.samples] == [
        0 * MS,
        10 * MS,
        15 * MS,
        20 * MS,
    ]
    assert [[value.observation.value for value in sample.values] for sample in result.samples] == [
        [1.0, 2.0, 3.0],
        [10.0, 2.0, 3.0],
        [10.0, 20.0, 3.0],
        [10.0, 20.0, 30.0],
    ]

def test_bounded_policy_requires_explicit_age_and_basis():
    with pytest.raises(ValueError, match="max_age"):
        TemporalAlignmentPolicy(AlignmentPolicyKind.BOUNDED_PREVIOUS, basis="x")
    with pytest.raises(ValueError, match="basis"):
        TemporalAlignmentPolicy(AlignmentPolicyKind.BOUNDED_PREVIOUS, max_age=MS)
    with pytest.raises(ValueError, match="strict"):
        TemporalAlignmentPolicy(max_age=MS)


def test_alignment_policy_is_part_of_analysis_identity_without_changing_strict():
    # Pinned: identity of the default policy recorded before alignment policies.
    assert phase_unbalance_policy_digest() == (
        "054fb3002dd2e0a4883222f80b140d083cc1b80f8ffdb31ee360749007ddf1eb"
    )
    bounded_digest = phase_unbalance_policy_digest(PhaseUnbalanceConfig(alignment=BOUNDED))
    assert bounded_digest != phase_unbalance_policy_digest()

    same_computation = TemporalAlignmentPolicy(
        AlignmentPolicyKind.BOUNDED_PREVIOUS,
        max_age=50 * MS,
        basis="  another documented justification  ",
    )
    assert same_computation.basis == "another documented justification"
    assert same_computation.identity() != BOUNDED.identity()
    assert (
        phase_unbalance_policy_digest(PhaseUnbalanceConfig(alignment=same_computation))
        == bounded_digest
    )

    different_age = TemporalAlignmentPolicy(
        AlignmentPolicyKind.BOUNDED_PREVIOUS,
        max_age=40 * MS,
        basis="same device, stricter validated age",
    )
    assert (
        phase_unbalance_policy_digest(PhaseUnbalanceConfig(alignment=different_age))
        != bounded_digest
    )


def test_window_with_a_stable_phase_is_analyzed_only_under_an_explicit_bounded_policy():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_window_analysis_input import END, START, _event

    from industrial_phm.application import ObservationWindowBuffer

    buffer = ObservationWindowBuffer(
        window_id="stable-vc",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va", "vb", "vc"),
        window_start=START,
        window_end=END,
        max_buffered_events=16,
        max_future_skew_seconds=5.0,
    )
    # vc reports once (a stable phase); va/vb change every second.
    buffer.ingest(_event("vc", 10, 225.0, 0))
    for index, second in enumerate(range(10, 14), start=1):
        buffer.ingest(_event("va", second, 220.0 + index, 2 * index))
        buffer.ingest(_event("vb", second, 230.0 - index, 2 * index + 1))
    buffer.advance_watermark(END)
    window = buffer.finalize(finalized_at=END)

    strict = run_phase_unbalance_on_window(window)
    assert strict.evidence.results[0].evaluated_samples == 1
    assert strict.evidence.results[0].excluded_samples == {"incomplete-phases": 3}

    two_seconds = TemporalAlignmentPolicy(
        AlignmentPolicyKind.BOUNDED_PREVIOUS,
        max_age=timedelta(seconds=2),
        basis="synthetic fixture: vc refreshes at least every 2 s",
    )
    bounded = run_phase_unbalance_on_window(
        window, config=PhaseUnbalanceConfig(alignment=two_seconds)
    )
    voltage = bounded.evidence.results[0]
    assert voltage.evaluated_samples == 3
    assert voltage.excluded_samples == {"no-recent-phase-value": 1}
    assert (voltage.carried_values, voltage.max_carry_age_seconds) == (2, 2.0)
    assert bounded.evidence.config.alignment == two_seconds
