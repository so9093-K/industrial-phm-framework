"""Packaged demo command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.demo import (
    AihubBoilerDemoConfig,
    SyntheticDemoConfig,
    run_aihub_boiler_demo,
    run_synthetic_demo,
)
from industrial_phm.demo.xjtu_models import XjtuModelDemoConfig, prepare_xjtu_model_demo


def _run_demo_aihub_boiler(args: argparse.Namespace) -> int:
    try:
        preset = AihubBoilerDemoConfig(
            archive=args.archive,
            workspace=args.workspace,
            opcua_port=args.opcua_port,
            ui_port=args.ui_port,
            speed=args.speed,
            startup_timeout_seconds=args.startup_timeout_seconds,
        )
        return run_aihub_boiler_demo(preset)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"AI-Hub boiler demo failed: {error}", file=sys.stderr)
        return 1


def _run_demo_synthetic(args: argparse.Namespace) -> int:
    try:
        preset = SyntheticDemoConfig(
            workspace=args.workspace,
            opcua_port=args.opcua_port,
            ui_port=args.ui_port,
            publish_interval_seconds=args.publish_interval_seconds,
            startup_timeout_seconds=args.startup_timeout_seconds,
        )
        return run_synthetic_demo(preset)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"synthetic demo failed: {error}", file=sys.stderr)
        return 1


def _run_demo_xjtu(args: argparse.Namespace) -> int:
    from industrial_phm.commands.operations import _start_operations_workspace
    from industrial_phm.commands.phm import _checkout_revision
    from industrial_phm.runtime import port_in_use, supervisor_is_live
    from industrial_phm.runtime.operations_runtime import OPERATIONS_UI_HOST

    preset = XjtuModelDemoConfig(
        source=args.source,
        workspace=args.workspace,
        bearing=args.bearing,
        ui_port=args.ui_port,
        code_revision=args.code_revision,
    )
    try:
        prepared = prepare_xjtu_model_demo(
            preset, code_revision=_checkout_revision, report=lambda line: print(line, flush=True)
        )
    except (OSError, ValueError) as error:
        print(f"XJTU-SY model demo failed: {error}", file=sys.stderr)
        return 1
    print(
        f"workspace={prepared.workspace.root} bearing={preset.bearing} "
        f"delivered={prepared.replay.delivered} already_present={prepared.replay.already_present} "
        f"models={','.join(prepared.packages)} (recorded replay)",
        flush=True,
    )
    if not supervisor_is_live(prepared.workspace) and port_in_use(
        OPERATIONS_UI_HOST, preset.ui_port
    ):
        print(
            f"XJTU-SY model demo could not start: {OPERATIONS_UI_HOST}:{preset.ui_port} is in use; "
            "pass another --ui-port.",
            file=sys.stderr,
        )
        return 1
    return _start_operations_workspace(prepared.workspace, prepared.config)
