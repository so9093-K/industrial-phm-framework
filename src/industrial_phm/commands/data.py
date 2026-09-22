"""Dataset command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.adapters import (
    CsvSensorLayout,
    CsvSensorSourceError,
    ImsBearingSourceError,
    MimiiDueSourceError,
    XjtuSySourceError,
    validate_csv_sensor_source,
    validate_ims_source,
    validate_mimii_due_source,
    validate_xjtu_source,
)
from industrial_phm.data.acquisition import (
    ManualAcquisitionRequired,
    dataset_archive_path,
    fetch_dataset,
)
from industrial_phm.data.registry import UnknownDatasetError, get_dataset, list_datasets
from industrial_phm.data.validation import (
    DatasetIntegrityError,
    inspect_file,
    inspect_source,
    verify_sha256,
)


def _print_available_datasets() -> None:
    print(
        "available datasets: " + ", ".join(manifest.dataset_id for manifest in list_datasets()),
        file=sys.stderr,
    )


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
        _print_available_datasets()
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
        print("next: follow the dataset preparation guide in data/README.md")
        return 0

    present = path.is_file()
    print(f"archive: {path}")
    print(f"local state: {'present' if present else 'missing'}")
    checksum_policy = "manifest SHA-256" if manifest.sha256 is not None else "local SHA-256"
    print(f"checksum policy: {checksum_policy}")
    if present:
        print(f"next: industrial-phm data verify {manifest.dataset_id}")
    else:
        print(f"next: industrial-phm data fetch {manifest.dataset_id}")
    return 0


def _run_data_fetch(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
        result = fetch_dataset(manifest, args.root)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        _print_available_datasets()
        return 2
    except ManualAcquisitionRequired as error:
        print(str(error), file=sys.stderr)
        print(
            "download from the official source and preserve provenance before import",
            file=sys.stderr,
        )
        print("next: follow the dataset preparation guide in data/README.md", file=sys.stderr)
        return 2
    except (OSError, DatasetIntegrityError, ValueError) as error:
        print(f"dataset fetch failed: {error}", file=sys.stderr)
        return 1

    print(f"fetched: {result.path}")
    print(f"bytes: {result.integrity.size_bytes}")
    print(f"sha256: {result.integrity.sha256}")
    if not result.checksum_pinned:
        print("integrity basis: local SHA-256 provenance")
    print(
        f"next: industrial-phm data inspect {manifest.dataset_id} --source {result.path} --details"
    )
    return 0


def _run_data_verify(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        _print_available_datasets()
        return 2

    path = dataset_archive_path(manifest, root=args.root)
    if path is None:
        print(
            f"{manifest.dataset_id} is a manual source without a framework-managed archive",
            file=sys.stderr,
        )
        print(f"official source: {manifest.source_url}", file=sys.stderr)
        print("next: follow the dataset preparation guide in data/README.md", file=sys.stderr)
        return 2

    try:
        if manifest.sha256 is None:
            integrity = inspect_file(path)
        else:
            integrity = verify_sha256(path, manifest.sha256)
    except DatasetIntegrityError as error:
        print(str(error), file=sys.stderr)
        return 1

    if manifest.sha256 is None:
        print(f"local file inspected: {integrity.path}")
    else:
        print(f"verified local file: {integrity.path}")
    print(f"bytes: {integrity.size_bytes}")
    print(f"sha256: {integrity.sha256}")
    if manifest.sha256 is None:
        print("integrity basis: local SHA-256 provenance; no publisher checksum pinned")
    print(
        f"next: industrial-phm data inspect {manifest.dataset_id} "
        f"--source {integrity.path} --details"
    )
    return 0


def _run_data_inspect(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
        inspection = inspect_source(args.source)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        _print_available_datasets()
        return 2
    except (OSError, DatasetIntegrityError) as error:
        print(f"dataset inspection failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {manifest.dataset_id}")
    print(f"title: {manifest.title}")
    print(f"provider: {manifest.provider}")
    print(f"official source: {manifest.source_url}")
    print(f"local source: {inspection.path}")
    print(f"source kind: {inspection.kind}")
    print(f"files: {inspection.file_count}")
    print(f"bytes: {inspection.source_bytes}")
    if inspection.kind == "zip":
        print(f"uncompressed bytes: {inspection.total_bytes}")
    print(f"max path depth: {inspection.max_depth}")

    for summary in inspection.extension_summaries:
        extension = summary.extension or "<none>"
        print(
            f"extension {extension}: {summary.file_count} file(s), "
            f"{summary.total_bytes} payload byte(s)"
        )

    if args.details:
        for entry in inspection.top_level_entries:
            print(f"top-level sample: {entry}")
        for path_sample in inspection.representative_files:
            print(f"representative file: {path_sample}")

    if inspection.file_count == 0:
        print(
            "inspection state: empty local source; add dataset files before continuing",
            file=sys.stderr,
        )
        print("next: follow the dataset preparation guide in data/README.md", file=sys.stderr)
        return 1

    nested_archive_extensions = {".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".zip"}
    nested_archives_observed = inspection.kind == "zip" and any(
        summary.extension in nested_archive_extensions for summary in inspection.extension_summaries
    )
    print("inspection scope: structural inventory")
    print("inspection state: completed")
    if nested_archives_observed:
        print("prepared source state: nested archive extraction required")
        print("next: extract the nested archive as described in data/README.md")
    else:
        print("next: prepare the adapter source layout described in data/README.md")
    print(f"then: industrial-phm data validate {manifest.dataset_id} --source <prepared-source>")
    return 0


def _run_data_validate_csv(args: argparse.Namespace) -> int:
    try:
        layout = CsvSensorLayout(
            asset_id=args.asset_id,
            channel_columns=tuple(args.channels),
            timestamp_column=args.timestamp_column,
            sampling_rate_hz=args.sampling_rate_hz,
            sampling_rate_tolerance_ratio=args.sampling_rate_tolerance_ratio,
            minimum_sample_count=args.minimum_sample_count,
            delimiter=args.delimiter,
        )
        report = validate_csv_sensor_source(args.source, layout)
    except (CsvSensorSourceError, OSError, ValueError) as error:
        print(f"field CSV validation failed: {error}", file=sys.stderr)
        return 1

    print("source kind: field-csv")
    print(f"asset: {report.asset_id}")
    print(f"local source: {report.source}")
    print(f"samples: {report.sample_count}")
    print(f"channels: {', '.join(report.channels)}")
    if report.timestamp_column is not None:
        print(f"timestamp column: {report.timestamp_column}")
        if report.first_timestamp is not None:
            print(f"first timestamp: {report.first_timestamp.isoformat()}")
        if report.last_timestamp is not None:
            print(f"last timestamp: {report.last_timestamp.isoformat()}")
        if report.minimum_interval_seconds is not None:
            print(f"minimum interval seconds: {report.minimum_interval_seconds:g}")
        if report.maximum_interval_seconds is not None:
            print(f"maximum interval seconds: {report.maximum_interval_seconds:g}")
    if report.sampling_rate_hz is not None:
        print(f"sampling rate hz: {report.sampling_rate_hz:g}")
    if report.maximum_sampling_interval_deviation_ratio is not None:
        print(
            "maximum sampling interval deviation ratio: "
            f"{report.maximum_sampling_interval_deviation_ratio:g}"
        )
    print(f"bytes: {report.source_size_bytes}")
    print(f"sha256: {report.source_sha256}")

    if report.quality_issues:
        print("quality state: WARN")
        for issue in report.quality_issues:
            print(f"quality {issue.severity.value} [{issue.code}]: {issue.message}")
    else:
        print("quality state: PASS")
    print("canonical mapping: READY")
    print("scope: source validation only; no model fitting or thresholding performed")
    return 0


def _run_data_validate(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        _print_available_datasets()
        return 2

    if manifest.dataset_id == "xjtu-sy":
        return _run_xjtu_data_validate(args, manifest.title)
    if manifest.dataset_id == "ims-bearings":
        return _run_ims_data_validate(args, manifest.title)
    if manifest.dataset_id == "mimii-due":
        return _run_mimii_data_validate(args, manifest.title)

    print(
        f"dataset-specific validation is not implemented for {manifest.dataset_id}",
        file=sys.stderr,
    )
    return 2


def _run_mimii_data_validate(args: argparse.Namespace, title: str) -> int:
    try:
        report = validate_mimii_due_source(args.source, full=args.full)
    except (OSError, MimiiDueSourceError) as error:
        print(f"dataset validation failed: {error}", file=sys.stderr)
        return 1

    print("dataset: mimii-due")
    print(f"title: {title}")
    print(f"local source: {report.source}")
    print(f"validation mode: {'full' if report.full else 'sampled'}")
    print(f"machines: {report.machine_count}")
    print(f"sections: {report.section_count}")
    print(f"clips: {report.clip_count}")
    print(f"train clips: {report.train_clip_count}")
    print(f"test clips: {report.test_clip_count}")
    print(f"WAV headers checked: {report.checked_wav_count}")
    print(f"channels: {report.channels}")
    print(f"sample width bits: {report.sample_width_bits}")
    print(f"sampling rate hz: {report.sampling_rate_hz:g}")
    print(f"frames per clip: {report.frames_per_clip}")
    print(f"duration seconds: {report.duration_seconds:g}")
    print(f"WAV header compatibility: PASS ({'full' if report.full else 'sampled'})")

    if not report.profile_matches:
        print("profile compatibility: FAIL")
        for issue in report.profile_issues:
            print(f"profile issue: {issue}", file=sys.stderr)
        return 1

    print("profile compatibility: PASS")
    print("next: see docs/research/README.md for the matching experiment workflow")
    return 0


def _run_xjtu_data_validate(args: argparse.Namespace, title: str) -> int:

    try:
        report = validate_xjtu_source(args.source, full=args.full)
    except (OSError, XjtuSySourceError) as error:
        print(f"dataset validation failed: {error}", file=sys.stderr)
        return 1

    print("dataset: xjtu-sy")
    print(f"title: {title}")
    print(f"local source: {report.source}")
    print(f"validation mode: {'full' if report.full else 'sampled'}")
    print(f"operating conditions: {report.operating_condition_count}")
    print(f"bearing runs: {report.bearing_run_count}")
    print(f"acquisitions: {report.acquisition_count}")
    print(f"waveform acquisitions checked: {report.checked_acquisition_count}")
    print(f"samples per acquisition: {report.samples_per_acquisition}")
    print(f"channels: {', '.join(report.channels)}")
    print(f"sampling rate hz: {report.sampling_rate_hz:g}")
    print(f"waveform compatibility: PASS ({'full' if report.full else 'sampled'})")

    if not report.profile_matches:
        print("profile compatibility: FAIL")
        for issue in report.profile_issues:
            print(f"profile issue: {issue}", file=sys.stderr)
        return 1

    print("profile compatibility: PASS")
    print(
        "next: uv run --locked --group research --extra deep-learning "
        "marimo run apps/analysis_explorer.py"
    )
    return 0


def _run_ims_data_validate(args: argparse.Namespace, title: str) -> int:
    try:
        report = validate_ims_source(args.source, full=args.full)
    except (OSError, ImsBearingSourceError) as error:
        print(f"dataset validation failed: {error}", file=sys.stderr)
        return 1

    print("dataset: ims-bearings")
    print(f"title: {title}")
    print(f"local source: {report.source}")
    print(f"validation mode: {'full' if report.full else 'sampled'}")
    print(f"tests: {len(report.tests)}")
    print(f"acquisitions: {report.acquisition_count}")
    print(f"waveform acquisitions checked: {report.checked_acquisition_count}")
    print(f"samples per acquisition: {report.samples_per_acquisition}")
    print(f"sampling rate hz: {report.sampling_rate_hz:g}")
    for summary in report.tests:
        print(
            f"test {summary.test_id}: source={summary.source_directory}, "
            f"acquisitions={summary.acquisition_count}, channels={summary.channel_count}, "
            f"range={summary.first_acquisition_at.isoformat()}.."
            f"{summary.last_acquisition_at.isoformat()}"
        )
        if summary.archive_extension_acquisition_count:
            print(
                f"test {summary.test_id} archive extension: "
                f"{summary.archive_extension_acquisition_count} acquisition(s); "
                f"README scope={summary.readme_acquisition_count} acquisition(s)"
            )
    print(f"waveform compatibility: PASS ({'full' if report.full else 'sampled'})")

    if not report.profile_matches:
        print("profile compatibility: FAIL")
        for issue in report.profile_issues:
            print(f"profile issue: {issue}", file=sys.stderr)
        return 1

    print("profile compatibility: PASS")
    print("next: see docs/research/README.md for the matching experiment workflow")
    return 0
