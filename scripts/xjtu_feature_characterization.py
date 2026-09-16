"""Generate local XJTU-SY feature characterization artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from industrial_phm.experiments import characterize_xjtu_source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate vibration-statistical-v1 feature and descriptive characterization "
            "artifacts for one complete prepared XJTU-SY source."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Prepared XJTU-SY dataset root consumed by XjtuSyAdapter.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Local output directory for generated CSV/JSON research artifacts.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifacts = characterize_xjtu_source(args.source, args.output_dir)
    print(f"feature_set_id={artifacts.feature_set_id}")
    print(f"acquisitions={artifacts.acquisition_count}")
    print(f"bearing_runs={artifacts.bearing_run_count}")
    print(f"operating_conditions={artifacts.operating_condition_count}")
    print(f"feature_table={artifacts.feature_table_path}")
    print(f"summary={artifacts.summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
