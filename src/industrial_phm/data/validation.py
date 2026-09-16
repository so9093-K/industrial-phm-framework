"""Reusable integrity and local-source checks for acquired dataset data."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class DatasetIntegrityError(ValueError):
    """Raised when an acquired dataset source fails an explicit integrity check."""


@dataclass(frozen=True, slots=True)
class FileIntegrity:
    """Observed integrity metadata for a local file."""

    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SourceInspection:
    """Observed inventory summary for a local dataset source path."""

    path: Path
    kind: Literal["file", "directory"]
    file_count: int
    total_bytes: int


def inspect_file(path: Path) -> FileIntegrity:
    """Return size and SHA-256 for a local regular file."""

    if not path.is_file():
        raise DatasetIntegrityError(f"dataset file does not exist: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return FileIntegrity(path=path, size_bytes=path.stat().st_size, sha256=digest.hexdigest())


def inspect_source(path: Path) -> SourceInspection:
    """Summarize a local file or directory without claiming upstream authenticity."""

    if path.is_file():
        return SourceInspection(
            path=path,
            kind="file",
            file_count=1,
            total_bytes=path.stat().st_size,
        )

    if not path.is_dir():
        raise DatasetIntegrityError(f"dataset source does not exist: {path}")

    file_count = 0
    total_bytes = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            file_count += 1
            total_bytes += entry.stat().st_size

    return SourceInspection(
        path=path,
        kind="directory",
        file_count=file_count,
        total_bytes=total_bytes,
    )


def verify_sha256(path: Path, expected_sha256: str) -> FileIntegrity:
    """Inspect a file and reject it when its SHA-256 differs from the manifest."""

    integrity = inspect_file(path)
    normalized = expected_sha256.lower()
    if integrity.sha256 != normalized:
        raise DatasetIntegrityError(
            f"dataset checksum mismatch for {path}: expected {normalized}, got {integrity.sha256}"
        )
    return integrity
