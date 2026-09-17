"""Reusable integrity and local-source checks for acquired dataset data."""

from __future__ import annotations

import hashlib
from bisect import insort
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from zipfile import BadZipFile, ZipFile, is_zipfile


class DatasetIntegrityError(ValueError):
    """Raised when an acquired dataset source fails an explicit integrity check."""


@dataclass(frozen=True, slots=True)
class FileIntegrity:
    """Observed integrity metadata for a local file."""

    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SourceExtensionSummary:
    """Observed file-count and payload-size summary for one filename extension."""

    extension: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True, slots=True)
class SourceInspection:
    """Observed structural inventory for a local dataset source path.

    ``total_bytes`` describes payload bytes. For a ZIP archive this is the sum of
    uncompressed member sizes while ``source_bytes`` is the archive size on disk.
    Path samples are metadata only; file payload contents are not read by inspection.
    """

    path: Path
    kind: Literal["file", "directory", "zip"]
    file_count: int
    source_bytes: int
    total_bytes: int
    max_depth: int
    extension_summaries: tuple[SourceExtensionSummary, ...]
    top_level_entries: tuple[str, ...]
    representative_files: tuple[str, ...]


_INSPECTION_SAMPLE_LIMIT = 12


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
    """Summarize local source structure without claiming upstream authenticity.

    Directories are walked recursively. ZIP files are inspected through archive metadata
    without extracting or reading member payloads. Other regular files are summarized as
    one-file sources.
    """

    if path.is_file():
        if path.suffix.lower() == ".zip":
            if not is_zipfile(path):
                raise DatasetIntegrityError(f"dataset ZIP archive is not readable: {path}")
            return _inspect_zip_source(path)

        size = path.stat().st_size
        return _summarize_source_entries(
            path=path,
            kind="file",
            source_bytes=size,
            entries=((PurePosixPath(path.name), size),),
        )

    if not path.is_dir():
        raise DatasetIntegrityError(f"dataset source does not exist: {path}")

    return _summarize_source_entries(
        path=path,
        kind="directory",
        source_bytes=None,
        entries=_directory_entries(path),
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


def _directory_entries(path: Path) -> Iterable[tuple[PurePosixPath, int]]:
    for entry in path.rglob("*"):
        if entry.is_file():
            yield PurePosixPath(entry.relative_to(path).as_posix()), entry.stat().st_size


def _inspect_zip_source(path: Path) -> SourceInspection:
    try:
        with ZipFile(path) as archive:
            entries = (
                (PurePosixPath(member.filename), member.file_size)
                for member in archive.infolist()
                if not member.is_dir()
            )
            return _summarize_source_entries(
                path=path,
                kind="zip",
                source_bytes=path.stat().st_size,
                entries=entries,
            )
    except BadZipFile as error:
        raise DatasetIntegrityError(f"dataset ZIP archive is not readable: {path}") from error


def _summarize_source_entries(
    *,
    path: Path,
    kind: Literal["file", "directory", "zip"],
    source_bytes: int | None,
    entries: Iterable[tuple[PurePosixPath, int]],
) -> SourceInspection:
    file_count = 0
    total_bytes = 0
    max_depth = 0
    extension_counts: Counter[str] = Counter()
    extension_bytes: Counter[str] = Counter()
    top_level_entries: list[str] = []
    representative_files: list[str] = []

    for relative_path, size_bytes in entries:
        if not relative_path.parts:
            continue

        relative_name = relative_path.as_posix()
        extension = _conservative_extension(relative_path)

        file_count += 1
        total_bytes += size_bytes
        max_depth = max(max_depth, len(relative_path.parts))
        extension_counts[extension] += 1
        extension_bytes[extension] += size_bytes
        _keep_smallest_unique(top_level_entries, relative_path.parts[0])
        _keep_smallest_unique(representative_files, relative_name)

    summaries = tuple(
        SourceExtensionSummary(
            extension=extension,
            file_count=extension_counts[extension],
            total_bytes=extension_bytes[extension],
        )
        for extension in sorted(extension_counts)
    )

    observed_source_bytes = total_bytes if source_bytes is None else source_bytes
    return SourceInspection(
        path=path,
        kind=kind,
        file_count=file_count,
        source_bytes=observed_source_bytes,
        total_bytes=total_bytes,
        max_depth=max_depth,
        extension_summaries=summaries,
        top_level_entries=tuple(top_level_entries),
        representative_files=tuple(representative_files),
    )


def _conservative_extension(path: PurePosixPath) -> str:
    """Return a likely filename extension without treating timestamp suffixes as one."""

    suffix = path.suffix.lower()
    if not suffix:
        return ""

    token = suffix[1:]
    if len(token) > 16 or not token.isalnum() or not any(char.isalpha() for char in token):
        return ""
    return suffix


def _keep_smallest_unique(values: list[str], value: str) -> None:
    if value in values:
        return

    insort(values, value)
    if len(values) > _INSPECTION_SAMPLE_LIMIT:
        values.pop()
