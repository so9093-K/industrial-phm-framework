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
