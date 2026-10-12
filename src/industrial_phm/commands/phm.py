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
        "--binding-id",
        help="explicit binding ID; default derives one from package, source and asset",
    )
    bind.set_defaults(handler=_run_phm_bind)

    listing = phm_commands.add_parser("list", help="show bindings, health and progress")
    listing.add_argument("workspace", type=Path, help="local Operations workspace root")
    listing.set_defaults(handler=_run_phm_list)


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
    binding_id = args.binding_id or _derived_binding_id(package_id, args.source_id, args.asset_id)
    try:
        binding = PhmBinding(
            binding_id=binding_id,
            package_id=package_id,
            source_id=args.source_id,
            asset_id=args.asset_id,
            step_kind=package.manifest.input.step_kind,
            created_at=datetime.now(UTC),
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


def _derived_binding_id(package_id: str, source_id: str, asset_id: str) -> str:
    digest = hashlib.sha256(f"{package_id}\n{source_id}\n{asset_id}".encode()).hexdigest()
    return f"phm-{asset_id}-{digest[:10]}"
