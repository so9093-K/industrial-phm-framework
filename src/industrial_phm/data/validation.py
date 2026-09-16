"""Reusable integrity checks for acquired dataset files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class DatasetIntegrityError(ValueError):
    """Raised when an acquired file fails an explicit integrity check."""


@dataclass(frozen=True, slots=True)
class FileIntegrity:
    """Observed integrity metadata for a local file."""

    path: Path
    size_bytes: int
    sha256: str


def inspect_file(path: Path) -> FileIntegrity:
    """Return size and SHA-256 for a local regular file."""

    if not path.is_file():
        raise DatasetIntegrityError(f"dataset file does not exist: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return FileIntegrity(path=path, size_bytes=path.stat().st_size, sha256=digest.hexdigest())


def verify_sha256(path: Path, expected_sha256: str) -> FileIntegrity:
    """Inspect a file and reject it when its SHA-256 differs from the manifest."""

    integrity = inspect_file(path)
    normalized = expected_sha256.lower()
    if integrity.sha256 != normalized:
        raise DatasetIntegrityError(
            f"dataset checksum mismatch for {path}: expected {normalized}, got {integrity.sha256}"
        )
    return integrity
