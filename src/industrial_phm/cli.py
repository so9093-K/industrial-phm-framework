"""Command-line interface for explicit industrial PHM workflows."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from industrial_phm import __version__
from industrial_phm.data.acquisition import (
    ManualAcquisitionRequired,
    dataset_archive_path,
    fetch_dataset,
)
from industrial_phm.data.registry import UnknownDatasetError, get_dataset, list_datasets
from industrial_phm.data.validation import DatasetIntegrityError, inspect_file, verify_sha256

DATA_ROOT_ENV = "INDUSTRIAL_PHM_DATA_DIR"


def default_data_root() -> Path:
    """Return the explicit environment override or repository-local raw-data default."""

    configured = os.environ.get(DATA_ROOT_ENV)
    return Path(configured) if configured else Path("data/raw")


def build_parser() -> argparse.ArgumentParser:
    """Build the stable CLI surface for currently implemented features."""

    parser = argparse.ArgumentParser(prog="industrial-phm")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="show runtime and data-root information")
    doctor.set_defaults(handler=_run_doctor)

    data = subcommands.add_parser("data", help="inspect and acquire registered datasets")
    data_commands = data.add_subparsers(dest="data_command", required=True)

    data_list = data_commands.add_parser("list", help="list registered datasets")
    data_list.set_defaults(handler=_run_data_list)

    data_status = data_commands.add_parser("status", help="show source and local acquisition state")
    data_status.add_argument("dataset_id")
    _add_data_root_argument(data_status)
    data_status.set_defaults(handler=_run_data_status)

    data_fetch = data_commands.add_parser("fetch", help="explicitly acquire a registered dataset")
    data_fetch.add_argument("dataset_id")
    _add_data_root_argument(data_fetch)
    data_fetch.set_defaults(handler=_run_data_fetch)

    data_verify = data_commands.add_parser(
        "verify",
        help="inspect or verify a managed dataset archive",
    )
    data_verify.add_argument("dataset_id")
    _add_data_root_argument(data_verify)
    data_verify.set_defaults(handler=_run_data_verify)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.handler
    return int(handler(args))


def _add_data_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=default_data_root(),
        help=f"raw data root (default: ${DATA_ROOT_ENV} or data/raw)",
    )


def _run_doctor(args: argparse.Namespace) -> int:
    del args
    print(f"industrial-phm {__version__}")
    print(f"data root: {default_data_root()}")
    print(f"registered datasets: {len(list_datasets())}")
    return 0


def _run_data_list(args: argparse.Namespace) -> int:
    del args
    for manifest in list_datasets():
        print(
            f"{manifest.dataset_id}\t{manifest.provider}\t{manifest.version}\t"
            f"{manifest.license_name}\t{manifest.title}"
        )
    return 0


def _run_data_status(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    root = args.root
    print(f"dataset: {manifest.dataset_id}")
    print(f"title: {manifest.title}")
    print(f"version: {manifest.version}")
    print(f"provider: {manifest.provider}")
    print(f"source: {manifest.source_url}")
    print(f"license: {manifest.license_name}")
    if manifest.citation_doi is not None:
        print(f"citation DOI: {manifest.citation_doi}")

    path = dataset_archive_path(manifest, root)
    if path is None:
        print("local state: manual source; no framework-managed archive path")
        return 0

    print(f"archive: {path}")
    print(f"local state: {'present' if path.is_file() else 'missing'}")
    print(f"checksum policy: {'pinned' if manifest.sha256 is not None else 'not pinned'}")
    return 0


def _run_data_fetch(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
        result = fetch_dataset(manifest, args.root)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2
    except ManualAcquisitionRequired as error:
        print(str(error), file=sys.stderr)
        print(
            "download from the official source and preserve provenance before import",
            file=sys.stderr,
        )
        return 2
    except (OSError, DatasetIntegrityError, ValueError) as error:
        print(f"dataset fetch failed: {error}", file=sys.stderr)
        return 1

    print(f"fetched: {result.path}")
    print(f"bytes: {result.integrity.size_bytes}")
    print(f"sha256: {result.integrity.sha256}")
    if not result.checksum_pinned:
        print("integrity note: manifest does not pin an upstream checksum; digest is observational")
    return 0


def _run_data_verify(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    path = dataset_archive_path(manifest, args.root)
    if path is None:
        print(
            f"{manifest.dataset_id} is a manual source without a framework-managed archive",
            file=sys.stderr,
        )
        print(f"official source: {manifest.source_url}", file=sys.stderr)
        return 2

    try:
        if manifest.sha256 is None:
            integrity = inspect_file(path)
        else:
            integrity = verify_sha256(path, manifest.sha256)
    except DatasetIntegrityError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"verified local file: {integrity.path}")
    print(f"bytes: {integrity.size_bytes}")
    print(f"sha256: {integrity.sha256}")
    if manifest.sha256 is None:
        print(
            "integrity note: no checksum is pinned in the manifest; local digest only"
        )
    return 0
