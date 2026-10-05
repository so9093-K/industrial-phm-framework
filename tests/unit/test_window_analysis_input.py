import tracemalloc
from dataclasses import replace
from datetime import timedelta

import pytest

from industrial_phm.application import (
    JsonObservationWindowRepository,
    ObservationWindowBuffer,
    ObservationWindowEventDisposition,
)
from industrial_phm.application.alignment import AlignmentPolicyKind, TemporalAlignmentPolicy
from industrial_phm.application.analysis_input import (
    WindowInputReference,
    window_channel_observations,
    window_input_reference,
)
from industrial_phm.application.phase_unbalance import (
    PhaseUnbalanceAnalysis,
    PhaseUnbalanceConfig,
    phase_unbalance_policy_digest,
    run_phase_unbalance_on_window,
)
from industrial_phm.application.phase_unbalance_state import (
    JsonPhaseUnbalanceRepository,
    PhaseUnbalanceHistoryFormatError,
    SqlitePhaseUnbalanceRepository,
    window_result_key,
)

from tests.support.window_analysis import END, PHASES, START
from tests.support.window_analysis import window_event as _event


def _window(*, late_value=None):
    buffer = ObservationWindowBuffer(
        window_id="site-opcua:mcc-3:2026-09-29T12:00Z",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=tuple(PHASES),
        window_start=START,
        window_end=END,
        max_buffered_events=64,
        max_future_skew_seconds=5.0,
    )
    index = 0
    for second, volts, amps in (
        (10, (220, 230, 225), (10, 10, 13)),
        (20, (221, 229, 225), (0.2, 0.1, 0.3)),
    ):
        for channel, value in zip(
            ("va", "vb", "vc", "ia", "ib", "ic"), (*volts, *amps), strict=True
        ):
            assert buffer.ingest(_event(channel, second, value, index)).accepted
            index += 1
    # A replay of vb at 10 s with another value is accepted (new local identity)
    # and must be flagged conflicting, not averaged.
    assert buffer.ingest(_event("vb", 10, 231.0, 0, epoch=2)).accepted
    buffer.advance_watermark(START + timedelta(seconds=30))
    late = _event("va", 15, late_value or 999.0, 99)
    assert buffer.ingest(late).disposition == ObservationWindowEventDisposition.LATE
    buffer.advance_watermark(END)
    return buffer.finalize(finalized_at=END + timedelta(seconds=5))


def test_window_analysis_reads_only_accepted_events_with_their_own_semantics(tmp_path):
    window = _window()
    observations = window_channel_observations(window)
    conflicted = [o for o in observations if o.channel_id == "vb" and o.conflicting]
    assert len(conflicted) == 1 and conflicted[0].value is None
    assert all(o.value != 999.0 for o in observations)

    analysis = run_phase_unbalance_on_window(window)
    reference = analysis.evidence.input_reference
    assert isinstance(reference, WindowInputReference)
    assert reference.window_id == window.window_id
    assert (reference.accepted_event_count, reference.rejected_event_count) == (13, 1)
    voltage, current = analysis.evidence.results
    assert voltage.channels == ("va", "vb", "vc")
    assert voltage.channel_selection == "semantic-role"
    # 10 s is excluded as conflicting; only 20 s is evaluated.
    assert voltage.evaluated_samples == 1
    assert voltage.excluded_samples == {"conflicting-value": 1}
    assert voltage.median_percent == pytest.approx(4 / 225 * 100)
    assert current.evaluated_samples == 1  # 20 s is below the current signal threshold
    assert current.excluded_samples == {"low-signal": 1}

    # The late value never reaches the input: the digest ignores rejected events.
    assert window_input_reference(_window(late_value=1.0)).input_digest == reference.input_digest

    # Durable window evidence recomputes the same result; the record round-trips.
    windows = JsonObservationWindowRepository(tmp_path / "windows.json")
    windows.record_window(window)
    again = run_phase_unbalance_on_window(windows.get(window.window_id))
    assert again.evidence.results == analysis.evidence.results
    assert again.evidence.input_reference == reference
    results = JsonPhaseUnbalanceRepository(tmp_path / "unbalance.json")
    results.record(analysis)
    assert results.list_results() == (analysis,)


def test_window_events_without_snapshot_are_not_reinterpreted():
    buffer = ObservationWindowBuffer(
        window_id="w",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va", "vb", "vc"),
        window_start=START,
        window_end=END,
        max_buffered_events=8,
        max_future_skew_seconds=5.0,
    )
    for index, (channel, value) in enumerate((("va", 220), ("vb", 230), ("vc", 225))):
        buffer.ingest(_event(channel, 10, value, index, bound=channel != "vc"))
    buffer.advance_watermark(END)
    with pytest.raises(ValueError, match="no three-phase"):
        run_phase_unbalance_on_window(buffer.finalize(finalized_at=END))


def test_runner_analyzes_each_window_once_and_remembers_unanalyzable_windows(tmp_path):
    from industrial_phm.application import (
        JsonWindowAnalysisLedger,
        WindowAnalysisState,
        analyze_finalized_windows,
    )

    windows = JsonObservationWindowRepository(tmp_path / "windows.json")
    windows.record_window(_window())
    unbound = ObservationWindowBuffer(
        window_id="unbound",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va",),
        window_start=END,
        window_end=END + timedelta(minutes=1),
        max_buffered_events=4,
        max_future_skew_seconds=5.0,
    )
    unbound.ingest(_event("va", 70, 220.0, 50, bound=False))
    unbound.advance_watermark(END + timedelta(minutes=1))
    windows.record_window(unbound.finalize(finalized_at=END + timedelta(minutes=1)))
    results = JsonPhaseUnbalanceRepository(tmp_path / "unbalance.json")
    ledger = JsonWindowAnalysisLedger(tmp_path / "ledger.json")

    first = analyze_finalized_windows(windows, results, ledger)
    assert [(o.window_id, o.state) for o in first] == [
        (_window().window_id, WindowAnalysisState.ANALYZED),
        ("unbound", WindowAnalysisState.SKIPPED),
    ]
    assert "no three-phase" in first[1].reason
    # A restart finds both windows handled: nothing is analyzed or recorded again.
    restarted = JsonWindowAnalysisLedger(tmp_path / "ledger.json")
    assert analyze_finalized_windows(windows, results, restarted) == ()
    assert len(results.list_results()) == 1


def test_phase_unbalance_policy_digest_tracks_requested_analysis_policy():
    baseline = phase_unbalance_policy_digest()
    assert baseline == phase_unbalance_policy_digest(PhaseUnbalanceConfig())
    assert baseline != phase_unbalance_policy_digest(PhaseUnbalanceConfig(min_mean_current_a=2.0))
    assert baseline != phase_unbalance_policy_digest(
        PhaseUnbalanceConfig(voltage_channels=("va", "vb", "vc"))
    )


def test_runner_skip_is_scoped_to_analysis_policy(tmp_path):
    from industrial_phm.application import (
        JsonWindowAnalysisLedger,
        WindowAnalysisState,
        analyze_finalized_windows,
    )

    windows = JsonObservationWindowRepository(tmp_path / "windows-policy.json")
    windows.record_window(_window())
    results = JsonPhaseUnbalanceRepository(tmp_path / "unbalance-policy.json")
    ledger = JsonWindowAnalysisLedger(tmp_path / "ledger-policy.json")

    blocked = analyze_finalized_windows(
        windows,
        results,
        ledger,
        config=PhaseUnbalanceConfig(
            min_mean_voltage_v=1_000.0,
            min_mean_current_a=1_000.0,
        ),
    )
    assert len(blocked) == 1
    assert blocked[0].state == WindowAnalysisState.SKIPPED

    retried = analyze_finalized_windows(windows, results, ledger)
    assert len(retried) == 1
    assert retried[0].state == WindowAnalysisState.ANALYZED
    assert blocked[0].analysis_policy_digest != retried[0].analysis_policy_digest
    assert len(results.list_results()) == 1


def test_runner_result_identity_changes_with_analysis_policy(tmp_path):
    from industrial_phm.application import (
        JsonWindowAnalysisLedger,
        WindowAnalysisState,
        analyze_finalized_windows,
    )

    windows = JsonObservationWindowRepository(tmp_path / "windows-result-policy.json")
    windows.record_window(_window())
    results = JsonPhaseUnbalanceRepository(tmp_path / "unbalance-result-policy.json")
    ledger = JsonWindowAnalysisLedger(tmp_path / "ledger-result-policy.json")

    first = analyze_finalized_windows(windows, results, ledger)
    assert len(first) == 1
    assert first[0].state == WindowAnalysisState.ANALYZED

    changed = analyze_finalized_windows(
        windows,
        results,
        ledger,
        config=PhaseUnbalanceConfig(bucket_count=50),
    )
    assert len(changed) == 1
    assert changed[0].state == WindowAnalysisState.ANALYZED
    assert changed[0].analysis_policy_digest != first[0].analysis_policy_digest
    assert len(results.list_results()) == 2

    assert (
        analyze_finalized_windows(
            windows,
            results,
            ledger,
            config=PhaseUnbalanceConfig(bucket_count=50),
        )
        == ()
    )


def test_runner_result_identity_distinguishes_alignment_and_survives_reload(tmp_path):
    from industrial_phm.application import (
        JsonWindowAnalysisLedger,
        WindowAnalysisState,
        analyze_finalized_windows,
    )

    windows = JsonObservationWindowRepository(tmp_path / "windows-alignment-policy.json")
    windows.record_window(_window())
    result_path = tmp_path / "unbalance-alignment-policy.json"
    ledger_path = tmp_path / "ledger-alignment-policy.json"
    results = JsonPhaseUnbalanceRepository(result_path)
    ledger = JsonWindowAnalysisLedger(ledger_path)

    strict = analyze_finalized_windows(windows, results, ledger)
    assert len(strict) == 1
    assert strict[0].state == WindowAnalysisState.ANALYZED

    bounded_policy = TemporalAlignmentPolicy(
        AlignmentPolicyKind.BOUNDED_PREVIOUS,
        max_age=timedelta(seconds=30),
        basis="test fixture permits 30 s state reconstruction",
    )
    bounded_config = PhaseUnbalanceConfig(alignment=bounded_policy)
    bounded = analyze_finalized_windows(windows, results, ledger, config=bounded_config)
    assert len(bounded) == 1
    assert bounded[0].state == WindowAnalysisState.ANALYZED
    assert bounded[0].analysis_policy_digest != strict[0].analysis_policy_digest
    assert len(results.list_results()) == 2

    reloaded_results = JsonPhaseUnbalanceRepository(result_path)
    reloaded_ledger = JsonWindowAnalysisLedger(ledger_path)
    assert (
        analyze_finalized_windows(
            windows,
            reloaded_results,
            reloaded_ledger,
            config=bounded_config,
        )
        == ()
    )
    assert len(reloaded_results.list_results()) == 2


def test_incremental_runner_pages_forward_and_restores_policy_cursor(tmp_path):
    from industrial_phm.application import (
        SqliteObservationWindowRepository,
        SqliteWindowAnalysisLedger,
        WindowAnalysisState,
        analyze_finalized_windows_incremental,
    )

    windows = SqliteObservationWindowRepository(tmp_path / "windows.sqlite")
    windows.record_window(_window())
    unbound = ObservationWindowBuffer(
        window_id="unbound-incremental",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va",),
        window_start=END,
        window_end=END + timedelta(minutes=1),
        max_buffered_events=4,
        max_future_skew_seconds=5.0,
    )
    unbound.ingest(_event("va", 70, 220.0, 51, bound=False))
    unbound.advance_watermark(END + timedelta(minutes=1))
    windows.record_window(unbound.finalize(finalized_at=END + timedelta(minutes=1)))

    results = JsonPhaseUnbalanceRepository(tmp_path / "incremental-results.json")
    ledger_path = tmp_path / "incremental-ledger.sqlite"
    ledger = SqliteWindowAnalysisLedger(ledger_path)

    first = analyze_finalized_windows_incremental(
        windows,
        results,
        ledger,
        page_size=1,
    )
    assert len(first) == 1
    assert first[0].state == WindowAnalysisState.ANALYZED

    reloaded = SqliteWindowAnalysisLedger(ledger_path)
    second = analyze_finalized_windows_incremental(
        windows,
        results,
        reloaded,
        page_size=1,
    )
    assert len(second) == 1
    assert second[0].window_id == "unbound-incremental"
    assert second[0].state == WindowAnalysisState.SKIPPED
    assert "no three-phase" in second[0].reason

    assert (
        analyze_finalized_windows_incremental(
            windows,
            results,
            SqliteWindowAnalysisLedger(ledger_path),
            page_size=1,
        )
        == ()
    )
    assert len(results.list_results()) == 1
    assert [item.window_id for item in reloaded.list_skipped()] == ["unbound-incremental"]


def test_incremental_runner_uses_independent_cursor_per_analysis_policy(tmp_path):
    from industrial_phm.application import (
        SqliteObservationWindowRepository,
        SqliteWindowAnalysisLedger,
        WindowAnalysisState,
        analyze_finalized_windows_incremental,
    )

    windows = SqliteObservationWindowRepository(tmp_path / "policy-windows.sqlite")
    windows.record_window(_window())
    results = JsonPhaseUnbalanceRepository(tmp_path / "policy-results.json")
    ledger = SqliteWindowAnalysisLedger(tmp_path / "policy-ledger.sqlite")

    strict = analyze_finalized_windows_incremental(windows, results, ledger)
    assert len(strict) == 1
    assert strict[0].state == WindowAnalysisState.ANALYZED

    changed = analyze_finalized_windows_incremental(
        windows,
        results,
        ledger,
        config=PhaseUnbalanceConfig(bucket_count=50),
    )
    assert len(changed) == 1
    assert changed[0].state == WindowAnalysisState.ANALYZED
    assert changed[0].analysis_policy_digest != strict[0].analysis_policy_digest
    assert len(results.list_results()) == 2


@pytest.fixture(scope="module")
def template_result() -> PhaseUnbalanceAnalysis:
    return run_phase_unbalance_on_window(_window())


def _result(template: PhaseUnbalanceAnalysis, index: int) -> PhaseUnbalanceAnalysis:
    """A distinct window result: its own run, evidence and window identity."""
    run_id = f"analysis-run-{index:06d}"
    reference = replace(template.evidence.input_reference, window_id=f"window-{index:06d}")
    return PhaseUnbalanceAnalysis(
        run=replace(
            template.run,
            analysis_run_id=run_id,
            completed_at=template.run.completed_at + timedelta(seconds=index),
        ),
        evidence=replace(
            template.evidence,
            evidence_id=f"evidence-{index:06d}",
            analysis_run_id=run_id,
            input_reference=reference,
        ),
    )


def _peak_bytes_of_one_record(store: SqlitePhaseUnbalanceRepository, result) -> int:
    tracemalloc.start()
    try:
        store.record_window_result(result)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _peak_bytes_of_recent_query(store: SqlitePhaseUnbalanceRepository) -> tuple[int, int]:
    tracemalloc.start()
    try:
        results = store.list_recent_results(5)
        return tracemalloc.get_traced_memory()[1], len(results)
    finally:
        tracemalloc.stop()


def test_recording_one_window_result_does_not_scale_with_stored_results(tmp_path, template_result):
    """N = 10 vs N = 2,000 stored results: one more record costs the same memory.

    The JSON store reread and rewrote every stored result for each window, so its
    per-window memory and time grew linearly with history (Phase 10 runner growth).
    """
    small = SqlitePhaseUnbalanceRepository(tmp_path / "small.sqlite")
    large = SqlitePhaseUnbalanceRepository(tmp_path / "large.sqlite")
    for index in range(10):
        small.record_window_result(_result(template_result, index))
    for index in range(2_000):
        large.record_window_result(_result(template_result, index))

    small_peak = _peak_bytes_of_one_record(small, _result(template_result, 10_001))
    large_peak = _peak_bytes_of_one_record(large, _result(template_result, 10_002))

    assert large_peak < 2 * small_peak + 64 * 1024, (small_peak, large_peak)
    assert len(large.list_results()) == 2_001

    small_query_peak, small_count = _peak_bytes_of_recent_query(small)
    large_query_peak, large_count = _peak_bytes_of_recent_query(large)
    assert (small_count, large_count) == (5, 5)
    assert large_query_peak < 2 * small_query_peak + 64 * 1024, (
        small_query_peak,
        large_query_peak,
    )


def test_bounded_result_queries_filter_and_preserve_exact_review_lookup(tmp_path, template_result):
    store = SqlitePhaseUnbalanceRepository(tmp_path / "bounded.sqlite")
    expected = []
    for index in range(8):
        result = _result(template_result, index)
        asset_id = "asset-b" if index % 2 else "asset-a"
        reference = replace(result.evidence.input_reference, asset_id=asset_id)
        result = replace(
            result,
            run=replace(result.run, asset_id=asset_id),
            evidence=replace(result.evidence, input_reference=reference),
        )
        store.record_window_result(result)
        expected.append(result)

    assert store.count_results() == 8
    assert [item.run.analysis_run_id for item in store.list_recent_results(3)] == [
        "analysis-run-000007",
        "analysis-run-000006",
        "analysis-run-000005",
    ]
    assert [
        item.run.analysis_run_id for item in store.list_recent_results(2, asset_id="asset-b")
    ] == ["analysis-run-000007", "analysis-run-000005"]
    assert (
        len(store.list_recent_results(2, capability_id=template_result.evidence.capability_id)) == 2
    )
    exact = store.find_results(
        ["analysis-run-000007", "missing-run", "analysis-run-000001", "analysis-run-000007"]
    )
    assert exact == (expected[1], expected[7])
    with pytest.raises(ValueError, match="positive integer"):
        store.list_recent_results(0)


def test_store_keeps_run_identity_window_once_and_order(tmp_path, template_result):
    store = SqlitePhaseUnbalanceRepository(tmp_path / "results.sqlite")
    first, second = _result(template_result, 2), _result(template_result, 1)
    assert store.record_window_result(first) == first
    store.record(second)
    # Completed-time order, as the JSON store returned it.
    assert store.list_results() == (second, first)
    # An identical replay is accepted; a different result for the same run is not.
    store.record(first)
    with pytest.raises(ValueError, match="analysis_run_id already exists"):
        store.record(replace(first, evidence=replace(first.evidence, semantic_versions=("x",))))
    # One result per window and policy: a second writer gets the stored one back.
    rival = replace(
        _result(template_result, 99),
        evidence=replace(
            _result(template_result, 99).evidence,
            input_reference=first.evidence.input_reference,
        ),
    )
    assert window_result_key(rival) == window_result_key(first)
    assert store.record_window_result(rival) == first
    # Evidence identity belongs to one run.
    other = _result(template_result, 7)
    taken_id = first.evidence.evidence_id
    stolen = replace(other, evidence=replace(other.evidence, evidence_id=taken_id))
    with pytest.raises(ValueError, match="evidence_id already exists"):
        store.record(stolen)
    assert len(SqlitePhaseUnbalanceRepository(tmp_path / "results.sqlite").list_results()) == 2


def test_json_state_is_rejected_not_overwritten(tmp_path):
    legacy = tmp_path / "phase-unbalance.json"
    legacy.write_text('{"schema": "industrial-phm-phase-unbalance-v1", "results": []}\n')
    with pytest.raises(PhaseUnbalanceHistoryFormatError, match="not SQLite"):
        SqlitePhaseUnbalanceRepository(legacy)
    assert legacy.read_text().startswith('{"schema"')
