"""CLI handlers for PHM model bindings in one Operations workspace (ADR-0025)."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application.phm_analysis import (
    PhmAnalysisError,
    PhmBinding,
    SqlitePhmAnalysisStore,
)
from industrial_phm.models.package import ModelPackageError, load_model_package
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def add_phm_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    phm = commands.add_parser(
        "phm",
        help="bind verified model packages to asset streams and inspect their progress",
    )
    phm_commands = phm.add_subparsers(dest="phm_command", required=True)

    bind = phm_commands.add_parser(
        "bind",
        help="run one verified model package over one source/asset step stream",
    )
    bind.add_argument("workspace", type=Path, help="local Operations workspace root")
    bind.add_argument("--package", required=True, help="model package ID under <workspace>/models")
    bind.add_argument("--source-id", required=True, help="registered source ID of the stream")
    bind.add_argument("--asset-id", required=True, help="asset ID of the stream")
    bind.add_argument(
        "--measurement-point-id", help="exact window measurement point (default: no point)"
    )
    bind.add_argument(
        "--recorded-replay",
        action="store_true",
        help="declare that this stream replays recorded data; results and screens say so",
    )
    bind.add_argument(
        "--binding-id",
        help="explicit binding ID; default derives one from package, source and asset",
    )
    bind.set_defaults(handler=_run_phm_bind)

    listing = phm_commands.add_parser("list", help="show bindings, health and progress")
    listing.add_argument("workspace", type=Path, help="local Operations workspace root")
    listing.set_defaults(handler=_run_phm_list)

    package = phm_commands.add_parser(
        "package-xjtu",
        help="fit the frozen XJTU-SY fold-1 anomaly and RUL configurations as model packages",
    )
    package.add_argument("workspace", type=Path, help="local Operations workspace root")
    package.add_argument("--source", type=Path, required=True, help="prepared XJTU-SY root")
    package.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("docs/research/results"),
        help="directory holding the canonical XJTU research result JSON files",
    )
    package.add_argument("--code-revision", help="full Git SHA; default reads the checkout HEAD")
    package.set_defaults(handler=_run_phm_package_xjtu)

    electrical = phm_commands.add_parser(
        "package-aihub", help="fit one device's confirmed Training/raw reference windows"
    )
    electrical.add_argument("workspace", type=Path)
    electrical.add_argument("--archive", type=Path, required=True)
    electrical.add_argument("--member", required=True, help="exact profiled compressor ZIP member")
    electrical.add_argument(
        "--candidate", choices=("isolation-forest", "pca-residual"), required=True
    )
    electrical.add_argument(
        "--code-revision", help="full Git SHA; default requires a clean checkout"
    )
    electrical.set_defaults(handler=_run_phm_package_aihub)

    replay = phm_commands.add_parser(
        "replay-xjtu",
        help="deliver one recorded XJTU-SY bearing run as ordered acquisition snapshots",
    )
    replay.add_argument("workspace", type=Path, help="local Operations workspace root")
    replay.add_argument("--source", type=Path, required=True, help="prepared XJTU-SY root")
    replay.add_argument("--bearing", required=True, help="bearing run, e.g. Bearing1_1")
    replay.add_argument("--source-id", default="xjtu-sy-replay", help="stream source ID")
    replay.add_argument(
        "--interval-seconds",
        type=float,
        default=1.0,
        help="pause between deliveries (recorded period is 60 s; replay is time-compressed)",
    )
    replay.add_argument("--start", type=int, default=1, help="first acquisition index")
    replay.add_argument("--count", type=int, help="number of acquisitions; default all")
    replay.set_defaults(handler=_run_phm_replay_xjtu)


def _run_phm_bind(args: argparse.Namespace) -> int:
    workspace = OperationsWorkspace(args.workspace.resolve())
    if not workspace.config_path.is_file():
        print(f"phm bind failed: not an Operations workspace: {workspace.root}", file=sys.stderr)
        return 1
    package_id = str(args.package)
    if "/" in package_id or package_id.startswith("."):
        print("phm bind failed: invalid package ID", file=sys.stderr)
        return 1
    try:
        package = load_model_package(workspace.models_path / package_id)
    except ModelPackageError as error:
        print(f"phm bind failed: package not usable: {error}", file=sys.stderr)
        return 1
    binding_id = args.binding_id or _derived_binding_id(
        package_id, args.source_id, args.asset_id, args.measurement_point_id
    )
    try:
        binding = PhmBinding(
            binding_id=binding_id,
            package_id=package_id,
            source_id=args.source_id,
            asset_id=args.asset_id,
            step_kind=package.manifest.input.step_kind,
            created_at=datetime.now(UTC),
            recorded_replay=bool(args.recorded_replay),
            measurement_point_id=args.measurement_point_id,
        )
        created = SqlitePhmAnalysisStore(workspace.phm_analysis_path).create_binding(binding)
    except (PhmAnalysisError, OSError, sqlite3.Error) as error:
        print(f"phm bind failed: {error}", file=sys.stderr)
        return 1
    state = "created" if created else "already-present"
    print(f"binding={binding_id} package={package_id} {state}")
    print(f"task={package.manifest.output.task.value} step_kind={binding.step_kind.value}")
    return 0


def _run_phm_list(args: argparse.Namespace) -> int:
    workspace = OperationsWorkspace(args.workspace.resolve())
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    if not store.path.exists():
        print("no PHM bindings")
        return 0
    try:
        bindings = store.list_bindings()
        for binding in bindings:
            progress = store.progress(binding.binding_id)
            print(
                f"binding={binding.binding_id} package={binding.package_id} "
                f"source={binding.source_id} asset={binding.asset_id} "
                f"health={progress.health} position={progress.cursor_position}"
                + (f" reason={progress.health_reason}" if progress.health_reason else "")
            )
    except (PhmAnalysisError, OSError, sqlite3.Error) as error:
        print(f"phm list failed: {error}", file=sys.stderr)
        return 1
    if not bindings:
        print("no PHM bindings")
    return 0


def _run_phm_package_aihub(args: argparse.Namespace) -> int:
    from industrial_phm.adapters.aihub_power import archive_sha256
    from industrial_phm.experiments import aihub_electrical_anomaly as ev

    workspace = OperationsWorkspace(args.workspace.resolve())
    if not workspace.config_path.is_file():
        print("package failed: initialize an Operations workspace first", file=sys.stderr)
        return 1
    revision = args.code_revision or _checkout_revision()
    if revision is None:
        print("package failed: pass --code-revision outside a clean checkout", file=sys.stderr)
        return 1
    try:
        device = ev.load_device(
            args.archive, args.member, archive_sha256=archive_sha256(args.archive)
        )
        if device.ineligible_reason:
            raise ValueError(device.ineligible_reason)
        train, _holdout, boundary = ev.split_device(device.samples)
        if ev.running_count(train) < ev.MIN_TRAIN_RUNNING:
            raise ValueError("reference requires at least 2880 running timestamps")
        package = ev.build_device_package(
            args.candidate,
            ev.window_rows(train),
            workspace.models_path,
            device=device,
            boundary=boundary,
            created_at=datetime.now(UTC),
            code_revision=revision,
        )
    except (ValueError, OSError, ModelPackageError) as error:
        print(f"package failed: {error}", file=sys.stderr)
        return 1
    print(f"package={package.package_id} task=anomaly-score device={device.device_id}")
    print(f"reference_end={boundary.isoformat()} window_seconds=300")
    print("development candidate: acceptance not yet passed; no RUL lifetime evidence")
    return 0


def _run_phm_package_xjtu(args: argparse.Namespace) -> int:
    from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
    from industrial_phm.experiments.xjtu import get_xjtu_reference_split
    from industrial_phm.experiments.xjtu_operational_package import build_xjtu_fold_1_packages
    from industrial_phm.features import iter_vibration_features

    workspace = OperationsWorkspace(args.workspace.resolve())
    if not workspace.config_path.is_file():
        print(f"package failed: not an Operations workspace: {workspace.root}", file=sys.stderr)
        return 1
    revision = args.code_revision or _checkout_revision()
    if revision is None:
        print("package failed: pass --code-revision outside a clean Git checkout", file=sys.stderr)
        return 1
    try:
        report = validate_xjtu_source(args.source)
        if not report.profile_matches:
            raise ValueError("XJTU-SY source does not match the complete profile")
        fold = next(f for f in get_xjtu_reference_split().folds if f.fold_id == "fold-1")
        print(f"extracting train features from {len(fold.train)} bearing runs ...", flush=True)
        train = tuple(
            iter_vibration_features(XjtuSyAdapter().iter_asset_series(args.source, fold.train))
        )
        manifests = build_xjtu_fold_1_packages(
            train,
            workspace.models_path,
            created_at=datetime.now(UTC),
            code_revision=revision,
            evidence_root=args.evidence_root,
        )
    except (ValueError, OSError, ModelPackageError) as error:
        print(f"package failed: {error}", file=sys.stderr)
        return 1
    for manifest in manifests:
        print(f"package={manifest.package_id} task={manifest.output.task.value}")
    return 0


def _run_phm_replay_xjtu(args: argparse.Namespace) -> int:
    from industrial_phm.application.acquisition_snapshot import (
        AcquisitionSnapshot,
        AcquisitionSnapshotError,
        SqliteAcquisitionSnapshotRepository,
    )
    from industrial_phm.demo.xjtu_snapshot_replay import replay_xjtu_bearing

    workspace = OperationsWorkspace(args.workspace.resolve())
    if not workspace.config_path.is_file():
        print(f"replay failed: not an Operations workspace: {workspace.root}", file=sys.stderr)
        return 1

    def report(snapshot: AcquisitionSnapshot) -> None:
        print(f"delivered asset={snapshot.asset_id} acquisition={snapshot.ordinal}", flush=True)

    try:
        progress = replay_xjtu_bearing(
            SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
            args.source,
            asset_id=args.bearing,
            source_id=args.source_id,
            interval_seconds=args.interval_seconds,
            start=args.start,
            count=args.count,
            on_delivered=report,
        )
    except KeyboardInterrupt:
        print("replay interrupted; delivered acquisitions are kept", file=sys.stderr)
        return 130
    except (ValueError, OSError, AcquisitionSnapshotError, sqlite3.Error) as error:
        print(f"replay failed: {error}", file=sys.stderr)
        return 1
    print(
        f"replay asset={progress.asset_id} delivered={progress.delivered} "
        f"already_present={progress.already_present} last={progress.last_ordinal} (recorded replay)"
    )
    return 0


def _checkout_revision() -> str | None:
    import subprocess

    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return None
    return None if dirty or len(head) != 40 else head


def _derived_binding_id(
    package_id: str, source_id: str, asset_id: str, point_id: str | None = None
) -> str:
    identity = f"{package_id}\n{source_id}\n{asset_id}"
    if point_id is not None:
        identity += "\npoint:" + point_id
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"phm-{asset_id}-{digest[:10]}"
