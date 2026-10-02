"""One-command synthetic three-phase Operations demo."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import math
import signal
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from industrial_phm.application import (
    ChannelSemanticBinding,
    CollectionDesiredState,
    JsonSourceRepository,
    MeasurementDefinition,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    request_collection_state,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import (
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsRuntimeConfig,
    OperationsSupervisorStateKind,
    OperationsUiConfig,
    OperationsWorkspace,
    SqliteCollectionControlRepository,
    build_operations_runtime_plan,
    initialize_operations_workspace,
    run_operations_supervisor,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from industrial_phm.demo.process import (
    DemoChildProcess,
    launch_logged_process,
    stop_demo_child,
    wait_for_loopback_listener,
)
from industrial_phm.demo.workspace import require_unclaimed_demo_workspace

SYNTHETIC_DEMO_ASSET_ID = "demo-motor-01"
SYNTHETIC_DEMO_SOURCE_ID = "demo-3phase-opcua"
SYNTHETIC_DEMO_CHANNELS = {
    "Voltage_L1": ("phase voltage", "R", "V"),
    "Voltage_L2": ("phase voltage", "S", "V"),
    "Voltage_L3": ("phase voltage", "T", "V"),
    "Current_L1": ("phase current", "R", "A"),
    "Current_L2": ("phase current", "S", "A"),
    "Current_L3": ("phase current", "T", "A"),
}
_DEFAULT_ENDPOINT_PATH = "/phm-demo/"


@dataclass(frozen=True, slots=True)
class SyntheticDemoConfig:
    """Local-only preset owned by the synthetic demo command."""

    workspace: Path = Path("artifacts/demo-synthetic")
    opcua_port: int = 4841
    ui_port: int = 2718
    publish_interval_seconds: float = 1.0
    startup_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, Path):
            raise ValueError("workspace must be Path")
        _validate_port(self.opcua_port, "opcua_port")
        _validate_port(self.ui_port, "ui_port")
        _validate_positive_finite(self.publish_interval_seconds, "publish_interval_seconds")
        _validate_positive_finite(self.startup_timeout_seconds, "startup_timeout_seconds")
        if self.opcua_port == self.ui_port:
            raise ValueError("opcua_port and ui_port must be different")

    @property
    def endpoint(self) -> str:
        return f"opc.tcp://127.0.0.1:{self.opcua_port}{_DEFAULT_ENDPOINT_PATH}"


@dataclass(frozen=True, slots=True)
class SyntheticDemoPreparation:
    workspace: OperationsWorkspace
    config: OperationsRuntimeConfig
    source_id: str
    endpoint: str
    created_workspace: bool


def _semantic_bindings() -> tuple[ChannelSemanticBinding, ...]:
    return tuple(
        ChannelSemanticBinding(
            source_id=SYNTHETIC_DEMO_SOURCE_ID,
            channel_id=channel,
            version="demo-three-phase-semantics-v1",
            definition=MeasurementDefinition(
                observed_property,
                scope=f"phase {phase}",
                unit=unit,
                unit_evidence="synthetic demo simulator definition",
            ),
            interpretation_evidence="synthetic demo mapping; not a physical meter",
        )
        for channel, (observed_property, phase, unit) in SYNTHETIC_DEMO_CHANNELS.items()
    )


def _expected_source(endpoint: str, registered_at: datetime) -> RegisteredSource:
    return RegisteredSource(
        source_id=SYNTHETIC_DEMO_SOURCE_ID,
        name="Synthetic live three-phase motor feeder",
        config=OpcUaSourceConfig(
            endpoint_url=endpoint,
            asset_id=SYNTHETIC_DEMO_ASSET_ID,
            node_mappings=tuple(
                OpcUaNodeMapping(channel, f"ns=2;s={channel}")
                for channel in SYNTHETIC_DEMO_CHANNELS
            ),
            timeout_seconds=2.0,
            semantic_bindings=_semantic_bindings(),
        ),
        registered_at=registered_at,
    )


def prepare_synthetic_demo(
    preset: SyntheticDemoConfig,
    *,
    now: datetime | None = None,
) -> SyntheticDemoPreparation:
    """Prepare or safely reopen the dedicated synthetic demo workspace."""
    if not isinstance(preset, SyntheticDemoConfig):
        raise ValueError("preset must be SyntheticDemoConfig")
    prepared_at = datetime.now(UTC) if now is None else now
    if prepared_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    workspace = OperationsWorkspace(preset.workspace)
    initialization = initialize_operations_workspace(workspace)
    repository = JsonSourceRepository(workspace.source_registry_path)
    expected = _expected_source(preset.endpoint, prepared_at)
    sources = repository.list_sources()

    if not sources:
        if not initialization.created:
            require_unclaimed_demo_workspace(workspace)
        repository.register(expected)
        transition_source_lifecycle(
            repository,
            SYNTHETIC_DEMO_SOURCE_ID,
            SourceLifecycleState.ACTIVE,
            changed_at=prepared_at,
        )
    else:
        if len(sources) != 1 or sources[0].source_id != SYNTHETIC_DEMO_SOURCE_ID:
            raise ValueError(
                "synthetic demo workspace contains non-demo registered sources; "
                "choose another --workspace"
            )
        existing = sources[0]
        if existing.name != expected.name or existing.config != expected.config:
            raise ValueError(
                "synthetic demo source configuration does not match this preset; "
                "choose another --workspace"
            )
        lifecycle = repository.get_lifecycle(SYNTHETIC_DEMO_SOURCE_ID)
        if lifecycle.state != SourceLifecycleState.ACTIVE:
            transition_source_lifecycle(
                repository,
                SYNTHETIC_DEMO_SOURCE_ID,
                SourceLifecycleState.ACTIVE,
                changed_at=prepared_at,
            )

    runtime_config = OperationsRuntimeConfig(
        collection=OperationsCollectionConfig(
            reconcile_interval_seconds=0.2,
            window_duration_seconds=10.0,
            allowed_lateness_seconds=2.0,
        ),
        analysis=OperationsAnalysisConfig(
            poll_interval_seconds=1.0,
            alignment="strict",
        ),
        ui=OperationsUiConfig(port=preset.ui_port),
    )
    write_operations_runtime_config(workspace.config_path, runtime_config)
    control = SqliteCollectionControlRepository(workspace.collection_control_path)
    request_collection_state(
        repository,
        repository,
        control,
        SYNTHETIC_DEMO_SOURCE_ID,
        CollectionDesiredState.RUNNING,
        requested_at=prepared_at,
    )
    return SyntheticDemoPreparation(
        workspace=workspace,
        config=runtime_config,
        source_id=SYNTHETIC_DEMO_SOURCE_ID,
        endpoint=preset.endpoint,
        created_workspace=initialization.created,
    )


def _three_phase_values(index: int) -> tuple[float, ...]:
    running = index % 60 < 45
    voltages = (
        230 + 2 * math.sin(index / 9),
        228 + 1.5 * math.cos(index / 11),
        231 + 0.5 * math.sin(index / 5),
    )
    load = 12 + 3 * math.sin(index / 6) if running else 0.2 + 0.01 * (index % 7)
    currents = (load, load * 0.96, load * 1.05)
    return (*voltages, *currents)


def validate_synthetic_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "opc.tcp" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ValueError("synthetic endpoint must use opc.tcp://127.0.0.1:<port>/...")


async def run_synthetic_opcua_server(
    endpoint: str,
    stop: asyncio.Event,
    *,
    interval_seconds: float = 1.0,
) -> None:
    """Publish explicit synthetic three-phase values on loopback only."""
    validate_synthetic_endpoint(endpoint)
    _validate_positive_finite(interval_seconds, "interval_seconds")
    asyncua = importlib.import_module("asyncua")
    ua = asyncua.ua
    server = asyncua.Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name("industrial-phm synthetic three-phase demo")
    namespace = await server.register_namespace("urn:industrial-phm:synthetic-three-phase")
    machine = await server.nodes.objects.add_object(namespace, "SyntheticMotor")
    nodes = [
        await machine.add_variable(ua.NodeId(channel, namespace), channel, 0.0)
        for channel in SYNTHETIC_DEMO_CHANNELS
    ]
    index = 0
    async with server:
        print(f"Synthetic OPC UA server: {endpoint}", flush=True)
        while not stop.is_set():
            timestamp = datetime.now(UTC)
            values = _three_phase_values(index)
            for node, value in zip(nodes, values, strict=True):
                await node.write_value(
                    ua.DataValue(
                        ua.Variant(value, ua.VariantType.Double),
                        SourceTimestamp=timestamp,
                        ServerTimestamp=timestamp,
                    )
                )
            index += 1
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)


def run_synthetic_demo(
    preset: SyntheticDemoConfig,
    *,
    process_launcher: Callable[[tuple[str, ...], Path], DemoChildProcess] | None = None,
    listener_probe: Callable[[str, int], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Prepare and run the simulator plus the normal Operations foreground runtime."""
    preparation = prepare_synthetic_demo(preset)
    simulator_log = preparation.workspace.logs_path / "synthetic-opcua.log"
    launch = launch_logged_process if process_launcher is None else process_launcher
    probe = _listener_ready if listener_probe is None else listener_probe
    simulator = launch(
        (
            sys.executable,
            "-m",
            "industrial_phm.demo.synthetic",
            "server",
            "--endpoint",
            preparation.endpoint,
            "--interval-seconds",
            str(preset.publish_interval_seconds),
        ),
        simulator_log,
    )
    simulator_exit_seen: list[int] = []
    try:
        wait_for_loopback_listener(
            preset.opcua_port,
            simulator,
            timeout_seconds=preset.startup_timeout_seconds,
            listener_probe=probe,
            sleep=sleep,
        )
        plan = build_operations_runtime_plan(preparation.workspace, preparation.config)
        print(
            f"demo=synthetic workspace={preparation.workspace.root} "
            f"operations_url={plan.ui_url} source={preparation.source_id}",
            flush=True,
        )

        def stop_requested() -> bool:
            return_code = simulator.poll()
            if return_code is None:
                return False
            simulator_exit_seen.append(return_code)
            return True

        result = run_operations_supervisor(plan, stop_requested=stop_requested)
        if simulator_exit_seen:
            print(
                "synthetic demo stopped because the OPC UA simulator exited "
                f"with code {simulator_exit_seen[-1]}",
                file=sys.stderr,
            )
            return 1
        if result.state.failure is not None:
            print(f"synthetic demo runtime failed: {result.state.failure}", file=sys.stderr)
            return 1
        if result.state.state == OperationsSupervisorStateKind.STOPPED:
            return 0
        return result.exit_code
    finally:
        stop_demo_child(simulator)


def server_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="industrial-phm synthetic OPC UA demo server")
    parser.add_argument("command", choices=("server",))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    async def run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        await run_synthetic_opcua_server(
            args.endpoint,
            stop,
            interval_seconds=args.interval_seconds,
        )

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 0
    return 0


def _validate_port(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{name} must be an integer between 1 and 65535")


def _validate_positive_finite(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")


if __name__ == "__main__":
    raise SystemExit(server_main())
