"""Shared synthetic window-analysis inputs used across test layers."""

from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    ChannelSemanticBinding,
    MeasurementDefinition,
    ObservationWindowBuffer,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.application.phase_unbalance import (
    PhaseUnbalanceAnalysis,
    run_phase_unbalance_on_window,
)
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification

START = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
END = START + timedelta(minutes=1)
PHASES = {"va": "R", "vb": "S", "vc": "T", "ia": "R", "ib": "S", "ic": "T"}


def window_event(
    channel: str,
    second: int,
    value: float,
    index: int,
    *,
    epoch: int = 1,
    bound: bool = True,
):
    """Build one projected OPC UA event with explicit test semantics."""

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


def finalized_window(window_id: str = "ops-render", start: datetime = START):
    """One finalized one-minute motor-7 window with bound R/S/T phase voltages.

    Event indexes follow the event time, so windows at different starts keep
    distinct delivery identities.
    """
    end = start + timedelta(minutes=1)
    buffer = ObservationWindowBuffer(
        window_id=window_id,
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va", "vb", "vc"),
        window_start=start,
        window_end=end,
        max_buffered_events=32,
        max_future_skew_seconds=5.0,
    )
    base = int((start - START).total_seconds())
    for second in range(10, 14):
        for offset, channel in enumerate(("va", "vb", "vc")):
            buffer.ingest(
                window_event(
                    channel,
                    base + second,
                    220.0 + offset + second,
                    3 * (base + second) + offset,
                )
            )
    buffer.advance_watermark(end)
    return buffer.finalize(finalized_at=end)


def phase_unbalance_analysis() -> PhaseUnbalanceAnalysis:
    """One finalized motor-7 window with bound R/S/T phase voltages, analyzed."""
    return run_phase_unbalance_on_window(finalized_window())
