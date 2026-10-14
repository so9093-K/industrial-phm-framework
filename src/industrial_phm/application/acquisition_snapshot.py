"""Ordered waveform acquisition snapshots as analysis steps (ADR-0025).

A snapshot is one high-rate waveform capture kept as file evidence: the repository records
where the file is, its SHA-256, channels, sampling and its ordinal within one asset stream. The
waveform itself is never expanded into Asset History rows. No absolute event time is invented;
``event_at`` is present only when the source supplied one.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from industrial_phm.contracts import CanonicalTimeSeries

_SCHEMA_VERSION = 1
_MetadataValue = str | int | float | bool | None


class AcquisitionSnapshotError(ValueError):
    """Raised when a snapshot record or its file evidence violates the contract."""


@dataclass(frozen=True, slots=True)
class AcquisitionSnapshot:
    source_id: str
    asset_id: str
    ordinal: int
    file_path: Path
    sha256: str
    channels: Sequence[str]
    sampling_rate_hz: float
    sample_count: int
    delivered_at: datetime
    replay: bool
    acquisition_period_seconds: float | None = None
    event_at: datetime | None = None
    metadata: Mapping[str, _MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("source_id", "asset_id"):
            _identifier(getattr(self, name), name)
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 1:
            raise AcquisitionSnapshotError("ordinal must be a positive integer")
        if not self.file_path.is_absolute():
            raise AcquisitionSnapshotError("file_path must be absolute")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise AcquisitionSnapshotError("sha256 must be a lowercase hex digest")
        channels = tuple(self.channels)
        if not channels or len(set(channels)) != len(channels):
            raise AcquisitionSnapshotError("channels must be unique and non-empty")
        object.__setattr__(self, "channels", channels)
        if not math.isfinite(self.sampling_rate_hz) or self.sampling_rate_hz <= 0:
            raise AcquisitionSnapshotError("sampling_rate_hz must be positive")
        if isinstance(self.sample_count, bool) or self.sample_count < 2:
            raise AcquisitionSnapshotError("sample_count must be at least two")
        if self.delivered_at.utcoffset() is None:
            raise AcquisitionSnapshotError("delivered_at must be timezone-aware")
        if self.event_at is not None and self.event_at.utcoffset() is None:
            raise AcquisitionSnapshotError("event_at must be timezone-aware when present")
        if self.acquisition_period_seconds is not None and not (
            math.isfinite(self.acquisition_period_seconds) and self.acquisition_period_seconds > 0
        ):
            raise AcquisitionSnapshotError("acquisition_period_seconds must be positive")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def step_key(self) -> str:
        return f"snapshot:{self.source_id}:{self.asset_id}:{self.ordinal}:{self.sha256}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_snapshot_waveform(snapshot: AcquisitionSnapshot) -> CanonicalTimeSeries:
    """Read the CSV waveform after proving the bytes are the recorded evidence."""
    try:
        data = snapshot.file_path.read_bytes()
    except OSError as error:
        raise AcquisitionSnapshotError("snapshot file is not readable") from error
    if hashlib.sha256(data).hexdigest() != snapshot.sha256:
        raise AcquisitionSnapshotError("snapshot file changed after delivery (SHA-256 mismatch)")
    reader = csv.reader(data.decode("utf-8-sig").splitlines())
    try:
        header = tuple(next(reader))
    except StopIteration as error:
        raise AcquisitionSnapshotError("snapshot CSV is empty") from error
    if header != tuple(snapshot.channels):
        raise AcquisitionSnapshotError("snapshot CSV header does not match recorded channels")
    width = len(header)
    values: list[tuple[float, ...]] = []
    for line_number, row in enumerate(reader, start=2):
        if len(row) != width:
            raise AcquisitionSnapshotError(f"snapshot CSV width mismatch at line {line_number}")
        try:
            values.append(tuple(float(cell) for cell in row))
        except ValueError as error:
            raise AcquisitionSnapshotError(
                f"non-numeric snapshot value at line {line_number}"
            ) from error
    if len(values) != snapshot.sample_count:
        raise AcquisitionSnapshotError("snapshot sample count differs from the recorded count")
    return CanonicalTimeSeries(
        asset_id=snapshot.asset_id,
        timestamps=None,
        channels=snapshot.channels,
        values=values,
        sampling_rate_hz=snapshot.sampling_rate_hz,
        metadata={**snapshot.metadata, "acquisition_index": snapshot.ordinal},
    )


class SqliteAcquisitionSnapshotRepository:
    """WAL-backed, append-only ordered snapshot streams keyed by (source, asset, ordinal)."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise AcquisitionSnapshotError("path must be pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def record(self, snapshot: AcquisitionSnapshot) -> bool:
        """Append a snapshot; return False when the identical snapshot already exists."""
        connection = self._connect()
        try:
            with connection:
                existing = connection.execute(
                    "SELECT sha256 FROM acquisition_snapshot "
                    "WHERE source_id = ? AND asset_id = ? AND ordinal = ?",
                    (snapshot.source_id, snapshot.asset_id, snapshot.ordinal),
                ).fetchone()
                if existing is not None:
                    if existing[0] != snapshot.sha256:
                        raise AcquisitionSnapshotError(
                            "a different snapshot is already recorded at this ordinal"
                        )
                    return False
                connection.execute(
                    "INSERT INTO acquisition_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        snapshot.source_id,
                        snapshot.asset_id,
                        snapshot.ordinal,
                        str(snapshot.file_path),
                        snapshot.sha256,
                        json.dumps(list(snapshot.channels)),
                        snapshot.sampling_rate_hz,
                        snapshot.sample_count,
                        snapshot.delivered_at.isoformat(),
                        int(snapshot.replay),
                        snapshot.acquisition_period_seconds,
                        None if snapshot.event_at is None else snapshot.event_at.isoformat(),
                        json.dumps(dict(snapshot.metadata), sort_keys=True),
                    ),
                )
            return True
        finally:
            connection.close()

    def list_after(
        self, source_id: str, asset_id: str, *, after_ordinal: int | None, limit: int = 500
    ) -> tuple[AcquisitionSnapshot, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM acquisition_snapshot WHERE source_id = ? AND asset_id = ? "
                "AND ordinal > ? ORDER BY ordinal LIMIT ?",
                (source_id, asset_id, after_ordinal or 0, limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_parse(row) for row in rows)

    def get(self, source_id: str, asset_id: str, ordinal: int) -> AcquisitionSnapshot | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM acquisition_snapshot WHERE source_id = ? AND asset_id = ? "
                "AND ordinal = ?",
                (source_id, asset_id, ordinal),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _parse(row)

    def list_streams(self) -> tuple[AcquisitionSnapshot, ...]:
        """The latest snapshot of every delivered (source, asset) stream."""
        if not self._path.exists():
            return ()
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT s.* FROM acquisition_snapshot s JOIN ("
                "SELECT source_id, asset_id, MAX(ordinal) AS ordinal FROM acquisition_snapshot "
                "GROUP BY source_id, asset_id) m USING (source_id, asset_id, ordinal) "
                "ORDER BY s.asset_id, s.source_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(_parse(row) for row in rows)

    def latest(self, source_id: str, asset_id: str) -> AcquisitionSnapshot | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM acquisition_snapshot WHERE source_id = ? AND asset_id = ? "
                "ORDER BY ordinal DESC LIMIT 1",
                (source_id, asset_id),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _parse(row)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=30.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS snapshot_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        current = connection.execute(
            "SELECT value FROM snapshot_meta WHERE key = 'schema_version'"
        ).fetchone()
        if current is None:
            connection.execute(
                "INSERT INTO snapshot_meta VALUES ('schema_version', ?)", (str(_SCHEMA_VERSION),)
            )
        elif current[0] != str(_SCHEMA_VERSION):
            connection.close()
            raise AcquisitionSnapshotError(f"unsupported snapshot schema: {current[0]!r}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS acquisition_snapshot(
                source_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                channels TEXT NOT NULL,
                sampling_rate_hz REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                delivered_at TEXT NOT NULL,
                replay INTEGER NOT NULL,
                acquisition_period_seconds REAL,
                event_at TEXT,
                metadata TEXT NOT NULL,
                PRIMARY KEY(source_id, asset_id, ordinal)
            )
            """
        )
        connection.commit()
        return connection


def _parse(row: Sequence[object]) -> AcquisitionSnapshot:
    return AcquisitionSnapshot(
        source_id=str(row[0]),
        asset_id=str(row[1]),
        ordinal=int(str(row[2])),
        file_path=Path(str(row[3])),
        sha256=str(row[4]),
        channels=tuple(json.loads(str(row[5]))),
        sampling_rate_hz=float(str(row[6])),
        sample_count=int(str(row[7])),
        delivered_at=datetime.fromisoformat(str(row[8])),
        replay=bool(row[9]),
        acquisition_period_seconds=None if row[10] is None else float(str(row[10])),
        event_at=None if row[11] is None else datetime.fromisoformat(str(row[11])),
        metadata=json.loads(str(row[12])),
    )


def _identifier(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 256
        or any(ord(c) < 32 for c in value)
    ):
        raise AcquisitionSnapshotError(f"{name} must be a printable trimmed identifier")
