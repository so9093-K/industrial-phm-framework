"""Feature command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.adapters import XjtuSySourceError
from industrial_phm.data.registry import UnknownDatasetError, get_dataset
from industrial_phm.experiments.xjtu_characterization import (
    XjtuFeatureCharacterizationError,
    characterize_xjtu_source,
)
from industrial_phm.features import VibrationFeatureError


def _run_feature_characterize(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"feature characterization is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        artifacts = characterize_xjtu_source(
            args.source,
            args.output_dir,
            fold_id=args.fold_id,
            partition=args.partition,
        )
    except (
        OSError,
        XjtuSySourceError,
        XjtuFeatureCharacterizationError,
        VibrationFeatureError,
    ) as error:
        print(f"feature characterization failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {manifest.dataset_id}")
    print(f"feature_set_id: {artifacts.feature_set_id}")
    print(f"split_id: {artifacts.split_id}")
    print(f"fold_id: {artifacts.fold_id}")
    print(f"partition: {artifacts.partition}")
    print(f"acquisitions: {artifacts.acquisition_count}")
    print(f"bearing_runs: {artifacts.bearing_run_count}")
    print(f"operating_conditions: {artifacts.operating_condition_count}")
    print(f"feature_table: {artifacts.feature_table_path}")
    print(f"summary: {artifacts.summary_path}")
    return 0
