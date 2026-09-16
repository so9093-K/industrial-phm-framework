"""Explicit dataset acquisition operations."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from industrial_phm import __version__
from industrial_phm.data.manifest import DatasetManifest
from industrial_phm.data.validation import FileIntegrity, inspect_file, verify_sha256


class ManualAcquisitionRequired(RuntimeError):
    """Raised when a source cannot be fetched safely by the framework."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Result of one explicit dataset fetch."""

    path: Path
    integrity: FileIntegrity
    checksum_pinned: bool


def dataset_archive_path(manifest: DatasetManifest, root: Path) -> Path | None:
    """Return the managed raw archive path for an automatically fetched dataset."""

    if manifest.archive_name is None:
        return None
    return root / manifest.dataset_id / manifest.archive_name


def fetch_dataset(
    manifest: DatasetManifest,
    root: Path,
    *,
    timeout_seconds: float = 120.0,
) -> FetchResult:
    """Fetch a registered URL source without extracting or mutating the vendor archive."""

    if manifest.provider == "manual":
        raise ManualAcquisitionRequired(
            f"{manifest.dataset_id} requires manual acquisition from {manifest.source_url}"
        )

    destination = dataset_archive_path(manifest, root)
    if destination is None:
        raise ValueError(f"dataset {manifest.dataset_id} has no managed archive name")

    if destination.is_file():
        return _result_for_existing_file(manifest, destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.part")
    request = Request(
        manifest.source_url,
        headers={"User-Agent": f"industrial-phm-framework/{__version__} dataset-acquisition"},
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response, temporary.open("wb") as target:
            shutil.copyfileobj(response, target)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return _result_for_existing_file(manifest, destination)


def _result_for_existing_file(manifest: DatasetManifest, path: Path) -> FetchResult:
    if manifest.sha256 is None:
        integrity = inspect_file(path)
        return FetchResult(path=path, integrity=integrity, checksum_pinned=False)

    integrity = verify_sha256(path, manifest.sha256)
    return FetchResult(path=path, integrity=integrity, checksum_pinned=True)
