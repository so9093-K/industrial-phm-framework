from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    ChannelSemanticBinding,
    JsonObservationWindowRepository,
    MeasurementDefinition,
    ObservationWindowBuffer,
    ObservationWindowEventDisposition,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.application.analysis_input import (
    WindowInputReference,
    window_channel_observations,
    window_input_reference,
)
from industrial_phm.application.phase_unbalance import (
    PhaseUnbalanceConfig,
    phase_unbalance_policy_digest,
    run_phase_unbalance_on_window,
)
from industrial_phm.application.phase_unbalance_state import JsonPhaseUnbalanceRepository
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification

START = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
END = START + timedelta(minutes=1)
PHASES = {"va": "R", "vb": "S", "vc": "T", "ia": "R", "ib": "S", "ic": "T"}


def _event(channel, second, value, index, *, epoch=1, bound=True):
    event_at = START + timedelta(seconds=second)
    quantity, unit = ("phase voltage", "V") if channel[0] == "v" else ("phase current", "A")
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="site-opcua",
        asset_id="motor-7",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="mcc-3",
        collection_index=index,
        notification=OpcUaSubscriptionNotification(
            observation=OpcUaNodeObservation(
                channel_id=channel,
                node_id=f"ns=2;s={channel}",
                value=value,
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=event_at,
                server_timestamp=None,
                received_at=event_at + timedelta(milliseconds=20),
            ),
            replayed=epoch > 1,
        ),
        semantic_binding=(
            ChannelSemanticBinding(
                source_id="site-opcua",
                channel_id=channel,
                version="site-semantics-v1",
                definition=MeasurementDefinition(
                    quantity,
                    scope=f"phase {PHASES[channel]}",
                    unit=unit,
                    unit_evidence="meter commissioning sheet",
                ),
                interpretation_evidence="commissioning record",
            )
            if bound
            else None
        ),
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=epoch,
        event_index=index,
        ingested_at=event_at + timedelta(milliseconds=30),
        event_time_policy=OpcUaEventTimePolicy(allow_server_timestamp_fallback=True),
    )


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
