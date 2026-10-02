"""Packaged demo command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.demo import SyntheticDemoConfig, run_synthetic_demo


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
