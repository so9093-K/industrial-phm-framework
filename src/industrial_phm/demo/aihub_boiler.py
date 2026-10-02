"""One-command AI-Hub 239 boiler replay on the normal Operations runtime."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
from industrial_phm.application import (
    CollectionDesiredState,
    JsonSourceRepository,
    SourceLifecycleState,
    request_collection_state,
    transition_source_lifecycle,
)
from industrial_phm.demo.aihub_replay import (
    MANIFEST,
    ReplaySelection,
    build_registered_replay_source,
    build_replay_manifest,
    load_selection,
    register_replay_source,
    write_replay_manifest,
)
from industrial_phm.demo.process import (
    DemoChildProcess,
    launch_logged_process,
    stop_demo_child,
    wait_for_loopback_listener,
)
from industrial_phm.demo.workspace import require_unclaimed_demo_workspace
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

AIHUB_BOILER_DEMO_SOURCE_ID = "aihub239-replay-boiler-2297"
AIHUB_BOILER_DEMO_ASSET_ID = "aihub-boiler-2297"
AIHUB_BOILER_DEMO_MEMBER = "5.보일러/SourceData_211.json"
AIHUB_BOILER_DEMO_START = datetime(2020, 11, 14, 6, 0)
AIHUB_BOILER_DEMO_END = datetime(2020, 11, 14, 12, 30)
AIHUB_BOILER_DEMO_DEFAULT_ARCHIVE = Path(
    "data/raw/aihub/239/archives/training/raw/5.보일러.zip"
)
AIHUB_BOILER_DEMO_ALIGNMENT_BASIS_PREFIX = (
    "AI-Hub 239 replay: every channel is written once per recorded minute"
)


@dataclass(frozen=True, slots=True)
class AihubBoilerDemoConfig:
    """Recorded boiler replay preset with only local execution choices exposed."""

    archive: Path = AIHUB_BOILER_DEMO_DEFAULT_ARCHIVE
    workspace: Path = Path("artifacts/demo-aihub-boiler")
    opcua_port: int = 4850
    ui_port: int = 2718
    speed: float = 60.0
    startup_timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not isinstance(self.archive, Path):
            raise ValueError("archive must be Path")
        if not isinstance(self.workspace, Path):
            raise ValueError("workspace must be Path")
        _validate_port(self.opcua_port, "opcua_port")
        _validate_port(self.ui_port, "ui_port")
        _validate_positive(self.speed, "speed")
        _validate_positive(self.startup_timeout_seconds, "startup_timeout_seconds")
        if self.opcua_port == self.ui_port:
            raise ValueError("opcua_port and ui_port must be different")

    @property
    def resolved_archive(self) -> Path:
        return self.archive.expanduser().resolve()

    @property
    def endpoint(self) -> str:
        return f"opc.tcp://127.0.0.1:{self.opcua_port}/aihub-replay/"

    @property
    def replay_record_interval_seconds(self) -> float:
        return 60.0 / self.speed

    @property
    def window_duration_seconds(self) -> float:
        return 30.0 * 60.0 / self.speed

    @property
    def max_carry_age_seconds(self) -> float:
        return 5.0 * 60.0 / self.speed

    @property
    def alignment_basis(self) -> str:
        return (
            f"{AIHUB_BOILER_DEMO_ALIGNMENT_BASIS_PREFIX} "
            f"({self.replay_record_interval_seconds:g} s replay time at {self.speed:g}x); "
            "unchanged values raise no DataChange; carry bounded to 5 recorded minutes "
            f"({self.max_carry_age_seconds:g} s replay time)"
        )


@dataclass(frozen=True, slots=True)
class AihubBoilerDemoPreparation:
    workspace: OperationsWorkspace
    config: OperationsRuntimeConfig
    selection: ReplaySelection
    source_id: str
    endpoint: str
    created_workspace: bool


def _binding() -> PowerHistoryBinding:
    return PowerHistoryBinding(
        source_id=AIHUB_BOILER_DEMO_SOURCE_ID,
        asset_id=AIHUB_BOILER_DEMO_ASSET_ID,
        device_id="2297",
        device_board_id="1",
        timezone="Asia/Seoul",
        identity_evidence=(
            "Explicit development grouping by source device/board; "
            "physical asset identity unverified"
        ),
        timezone_evidence=(
            "Explicit development normalization assumption Asia/Seoul; "
            "source timezone unverified"
        ),
        version="replay-v1",
    )


def _selection(preset: AihubBoilerDemoConfig) -> ReplaySelection:
    archive = preset.resolved_archive
    if not archive.is_file():
        raise OSError(
            "AI-Hub boiler archive is unavailable: "
            f"{archive}. Provide --archive or place the local archive at the default path."
        )
    return ReplaySelection(
        archive=archive,
        member=AIHUB_BOILER_DEMO_MEMBER,
        binding=_binding(),
        start_local=AIHUB_BOILER_DEMO_START,
        end_local=AIHUB_BOILER_DEMO_END,
    )


def prepare_aihub_boiler_demo(
    preset: AihubBoilerDemoConfig,
    *,
    now: datetime | None = None,
) -> AihubBoilerDemoPreparation:
    """Prepare or safely reopen the dedicated recorded-data demo workspace."""
    if not isinstance(preset, AihubBoilerDemoConfig):
        raise ValueError("preset must be AihubBoilerDemoConfig")
    prepared_at = datetime.now(UTC) if now is None else now
    if prepared_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    selection = _selection(preset)
    # Validate the archive/member/binding before creating any workspace state.
    manifest = build_replay_manifest(preset.endpoint, selection, prepared_at=prepared_at)

    workspace = OperationsWorkspace(preset.workspace)
    initialization = initialize_operations_workspace(workspace)
    repository = JsonSourceRepository(workspace.source_registry_path)
    sources = repository.list_sources()
    expected = build_registered_replay_source(
        selection,
        manifest,
        name="AI-Hub 239 recorded boiler power (OPC UA replay)",
        registered_at=prepared_at,
    )

    if not sources:
        if not initialization.created:
            require_unclaimed_demo_workspace(workspace)
        register_replay_source(
            workspace.root,
            selection,
            manifest,
            name=expected.name,
            desired_state=CollectionDesiredState.RUNNING,
            registered_at=prepared_at,
        )
        write_replay_manifest(workspace.root, manifest)
    else:
        if len(sources) != 1 or sources[0].source_id != AIHUB_BOILER_DEMO_SOURCE_ID:
            raise ValueError(
                "AI-Hub boiler demo workspace contains non-demo registered sources; "
                "choose another --workspace"
            )
        existing = sources[0]
        if existing.name != expected.name or existing.config != expected.config:
            raise ValueError(
                "AI-Hub boiler demo source configuration does not match this preset; "
                "choose another --workspace"
            )
        if not workspace.root.joinpath(MANIFEST).is_file():
            raise ValueError(
                "AI-Hub boiler demo replay manifest is missing; choose another --workspace"
            )
        existing_manifest, existing_selection = load_selection(workspace.root)
        if (
            existing_selection != selection
            or existing_manifest.get("endpoint") != preset.endpoint
        ):
            raise ValueError(
                "AI-Hub boiler demo replay selection does not match this preset; "
                "choose another --workspace"
            )
        lifecycle = repository.get_lifecycle(AIHUB_BOILER_DEMO_SOURCE_ID)
        if lifecycle.state != SourceLifecycleState.ACTIVE:
            transition_source_lifecycle(
                repository,
                AIHUB_BOILER_DEMO_SOURCE_ID,
                SourceLifecycleState.ACTIVE,
                changed_at=prepared_at,
            )
        request_collection_state(
            repository,
            repository,
            SqliteCollectionControlRepository(workspace.collection_control_path),
            AIHUB_BOILER_DEMO_SOURCE_ID,
            CollectionDesiredState.RUNNING,
            requested_at=prepared_at,
        )

    runtime_config = OperationsRuntimeConfig(
        collection=OperationsCollectionConfig(
            reconcile_interval_seconds=0.2,
            window_duration_seconds=preset.window_duration_seconds,
            allowed_lateness_seconds=2.0,
        ),
        analysis=OperationsAnalysisConfig(
            poll_interval_seconds=1.0,
            alignment="bounded-previous",
            max_carry_age_seconds=preset.max_carry_age_seconds,
            alignment_basis=preset.alignment_basis,
        ),
        ui=OperationsUiConfig(port=preset.ui_port),
    )
    write_operations_runtime_config(workspace.config_path, runtime_config)
    return AihubBoilerDemoPreparation(
        workspace=workspace,
        config=runtime_config,
        selection=selection,
        source_id=AIHUB_BOILER_DEMO_SOURCE_ID,
        endpoint=preset.endpoint,
        created_workspace=initialization.created,
    )


def run_aihub_boiler_demo(
    preset: AihubBoilerDemoConfig,
    *,
    process_launcher: Callable[[tuple[str, ...], Path], DemoChildProcess] | None = None,
    listener_probe: Callable[[str, int], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run recorded boiler replay plus the normal Operations foreground runtime."""
    preparation = prepare_aihub_boiler_demo(preset)
    replay_log = preparation.workspace.logs_path / "aihub-replay.log"
    launch = launch_logged_process if process_launcher is None else process_launcher
    replay = launch(
        (
            sys.executable,
            "-m",
            "industrial_phm.demo.aihub_replay",
            "server",
            "--root",
            str(preparation.workspace.root),
            "--speed",
            str(preset.speed),
            "--loop",
        ),
        replay_log,
    )
    replay_exit_seen: list[int] = []
    try:
        wait_for_loopback_listener(
            preset.opcua_port,
            replay,
            timeout_seconds=preset.startup_timeout_seconds,
            listener_probe=listener_probe,
            sleep=sleep,
        )
        plan = build_operations_runtime_plan(preparation.workspace, preparation.config)
        print(
            f"demo=aihub-boiler workspace={preparation.workspace.root} "
            f"operations_url={plan.ui_url} source={preparation.source_id} "
            f"archive={preparation.selection.archive} member={preparation.selection.member} "
            f"speed={preset.speed:g}x",
            flush=True,
        )

        def stop_requested() -> bool:
            return_code = replay.poll()
            if return_code is None:
                return False
            replay_exit_seen.append(return_code)
            return True

        result = run_operations_supervisor(plan, stop_requested=stop_requested)
        if replay_exit_seen:
            print(
                "AI-Hub boiler demo stopped because the replay server exited "
                f"with code {replay_exit_seen[-1]}",
                file=sys.stderr,
            )
            return 1
        if result.state.failure is not None:
            print(f"AI-Hub boiler demo runtime failed: {result.state.failure}", file=sys.stderr)
            return 1
        if result.state.state == OperationsSupervisorStateKind.STOPPED:
            return 0
        return result.exit_code
    finally:
        stop_demo_child(replay)


def _validate_port(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{name} must be an integer between 1 and 65535")


def _validate_positive(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise ValueError(f"{name} must be a positive number")
