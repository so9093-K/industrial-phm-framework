"""Durable human-review acknowledgement for validated analysis evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import hexdigits
from typing import cast

_REVIEW_SCHEMA_V1 = "industrial-phm-analysis-review-v1"
_ROOT_KEYS = frozenset({"schema", "records"})
_RECORD_KEYS = frozenset(
    {
        "artifact_path",
        "artifact_sha256",
        "asset_id",
        "review_policy_id",
        "review_threshold_value",
        "review_interval_count",
        "reviewed_at",
        "note",
    }
)


class AnalysisReviewFormatError(ValueError):
    """Raised when persisted analysis-review state is unsupported or invalid."""


@dataclass(frozen=True, slots=True)
class AnalysisReviewRecord:
    """One durable human acknowledgement of descriptive analysis review evidence.

    The record captures what the user reviewed. It is not an OperationalFinding,
    diagnosis, maintenance work order, or model output.
    """

    artifact_path: str
    artifact_sha256: str
    asset_id: str
    review_policy_id: str
    review_threshold_value: float
    review_interval_count: int
    reviewed_at: datetime
    note: str = ""

    def __post_init__(self) -> None:
        _validate_identifier(self.artifact_path, "artifact_path")
        _validate_sha256(self.artifact_sha256)
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.review_policy_id, "review_policy_id")
        if (
            isinstance(self.review_threshold_value, bool)
            or not isinstance(self.review_threshold_value, (int, float))
            or not math.isfinite(self.review_threshold_value)
        ):
            raise ValueError("review_threshold_value must be a finite number")
        if (
            isinstance(self.review_interval_count, bool)
            or not isinstance(self.review_interval_count, int)
            or self.review_interval_count <= 0
        ):
            raise ValueError("review_interval_count must be a positive integer")
        if not isinstance(self.reviewed_at, datetime) or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be a timezone-aware datetime")
        if not isinstance(self.note, str):
            raise ValueError("note must be a string")

    @property
    def key(self) -> tuple[str, str, str]:
        """Return stable evidence/review-policy identity for latest-state replacement."""
        return (self.artifact_sha256, self.asset_id, self.review_policy_id)


class JsonAnalysisReviewRepository:
    """Single-writer local JSON repository for durable review acknowledgements."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured review-state path."""
        return self._path

    def get(
        self,
        *,
        artifact_sha256: str,
        asset_id: str,
        review_policy_id: str,
    ) -> AnalysisReviewRecord | None:
        """Return the review for one analysis evidence scope, if it exists."""
        _validate_sha256(artifact_sha256)
        _validate_identifier(asset_id, "asset_id")
        _validate_identifier(review_policy_id, "review_policy_id")
        key = (artifact_sha256, asset_id, review_policy_id)
        return {record.key: record for record in self.list_records()}.get(key)

    def list_records(self) -> tuple[AnalysisReviewRecord, ...]:
        """Return all review records in deterministic evidence/asset/policy order."""
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"analysis review state path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise AnalysisReviewFormatError(
                "analysis review state must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "analysis review root")
        _require_exact_keys(root, _ROOT_KEYS, "analysis review root")
        schema = _require_string(root["schema"], "analysis review schema")
        if schema != _REVIEW_SCHEMA_V1:
            raise AnalysisReviewFormatError(
                f"unsupported analysis review schema: {schema!r}"
            )

        records_raw = root["records"]
        if not isinstance(records_raw, list):
            raise AnalysisReviewFormatError("analysis review records must be a JSON array")
        records = tuple(
            _parse_record(value, index=index) for index, value in enumerate(records_raw)
        )
        keys = tuple(record.key for record in records)
        if len(set(keys)) != len(keys):
            raise AnalysisReviewFormatError(
                "analysis review state contains duplicate evidence/asset/policy keys"
            )
        return tuple(sorted(records, key=lambda record: record.key))

    def record(self, record: AnalysisReviewRecord) -> None:
        """Persist or update one review without allowing reviewed_at regression."""
        if not isinstance(record, AnalysisReviewRecord):
            raise ValueError("record must be AnalysisReviewRecord")

        records = {item.key: item for item in self.list_records()}
        current = records.get(record.key)
        if current is not None:
            if record.reviewed_at < current.reviewed_at:
                raise ValueError("reviewed_at must not move backwards")
            if record.reviewed_at == current.reviewed_at and record != current:
                raise ValueError(
                    "review with the same reviewed_at must match persisted evidence"
                )
        records[record.key] = record
        self._write(tuple(records.values()))

    def _write(self, records: Sequence[AnalysisReviewRecord]) -> None:
        ordered = tuple(sorted(records, key=lambda record: record.key))
        payload = {
            "schema": _REVIEW_SCHEMA_V1,
            "records": [_serialize_record(record) for record in ordered],
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def analysis_artifact_sha256(path: Path) -> str:
    """Return exact byte identity for one analysis artifact."""
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")
    if not path.is_file():
        raise OSError(f"analysis artifact does not exist or is not a file: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _serialize_record(record: AnalysisReviewRecord) -> dict[str, object]:
    return {
        "artifact_path": record.artifact_path,
        "artifact_sha256": record.artifact_sha256,
        "asset_id": record.asset_id,
        "review_policy_id": record.review_policy_id,
        "review_threshold_value": record.review_threshold_value,
        "review_interval_count": record.review_interval_count,
        "reviewed_at": record.reviewed_at.isoformat(),
        "note": record.note,
    }


def _parse_record(value: object, *, index: int) -> AnalysisReviewRecord:
    label = f"analysis review records[{index}]"
    raw = _require_mapping(value, label)
    _require_exact_keys(raw, _RECORD_KEYS, label)
    try:
        return AnalysisReviewRecord(
            artifact_path=_require_string(raw["artifact_path"], f"{label}.artifact_path"),
            artifact_sha256=_require_string(
                raw["artifact_sha256"],
                f"{label}.artifact_sha256",
            ),
            asset_id=_require_string(raw["asset_id"], f"{label}.asset_id"),
            review_policy_id=_require_string(
                raw["review_policy_id"],
                f"{label}.review_policy_id",
            ),
            review_threshold_value=_require_number(
                raw["review_threshold_value"],
                f"{label}.review_threshold_value",
            ),
            review_interval_count=_require_integer(
                raw["review_interval_count"],
                f"{label}.review_interval_count",
            ),
            reviewed_at=datetime.fromisoformat(
                _require_string(raw["reviewed_at"], f"{label}.reviewed_at")
            ),
            note=_require_string(raw["note"], f"{label}.note"),
        )
    except ValueError as error:
        if isinstance(error, AnalysisReviewFormatError):
            raise
        raise AnalysisReviewFormatError(f"{label} is invalid: {error}") from error


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AnalysisReviewFormatError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise AnalysisReviewFormatError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AnalysisReviewFormatError(f"{label} must be a string")
    return value


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisReviewFormatError(f"{label} must be a number")
    return float(value)


def _require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalysisReviewFormatError(f"{label} must be an integer")
    return value


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_sha256(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("artifact_sha256 must be a string")
    has_invalid_character = any(character not in hexdigits for character in value)
    if len(value) != 64 or has_invalid_character:
        raise ValueError(
            "artifact_sha256 must contain exactly 64 hexadecimal characters"
        )
    if value != value.lower():
        raise ValueError("artifact_sha256 must use lowercase hexadecimal characters")
