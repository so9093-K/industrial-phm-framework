"""Durable latest receipt state for registered operational sources."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from industrial_phm.application.source_receipt import SourceReceiptEvidence

_RUNTIME_SCHEMA = "industrial-phm-source-runtime-v1"
_ROOT_KEYS = frozenset({"schema", "latest_receipts"})
_RECEIPT_KEYS = frozenset({"source_id", "observed_at", "received_at"})


class SourceRuntimeFormatError(ValueError):
    """Raised when persisted runtime receipt state is unsupported or invalid."""


@runtime_checkable
class SourceRuntimeRepository(Protocol):
    """Persistence boundary for latest accepted source receipt evidence."""

    def get_latest_receipt(self, source_id: str) -> SourceReceiptEvidence | None:
        """Return the latest accepted receipt for one source, if any."""
        ...

    def list_latest_receipts(self) -> tuple[SourceReceiptEvidence, ...]:
        """Return latest receipts in deterministic source-ID order."""
        ...

    def record_receipt(self, receipt: SourceReceiptEvidence) -> None:
        """Persist a latest receipt without allowing received_at regression."""
        ...


def validate_distinct_source_state_paths(
    registry_path: Path,
    runtime_path: Path,
) -> None:
    """Reject configuration that could let runtime writes overwrite control-plane state."""
    if not isinstance(registry_path, Path) or not isinstance(runtime_path, Path):
        raise ValueError("registry_path and runtime_path must be pathlib.Path values")
    if registry_path.expanduser().resolve(strict=False) == runtime_path.expanduser().resolve(
        strict=False
    ):
        raise ValueError("source runtime state path must differ from source registry path")


class JsonSourceRuntimeRepository:
    """Single-writer local JSON repository for latest source receipt evidence.

    This repository is separate from the source-registration control plane. It stores
    only the latest accepted receipt per source, not receipt history, connection
    health, ingestion status, retries, buffers, or freshness assessments.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured runtime-state file path."""
        return self._path

    def get_latest_receipt(self, source_id: str) -> SourceReceiptEvidence | None:
        _validate_source_id(source_id)
        return {receipt.source_id: receipt for receipt in self._read_receipts()}.get(source_id)

    def list_latest_receipts(self) -> tuple[SourceReceiptEvidence, ...]:
        return self._read_receipts()

    def record_receipt(self, receipt: SourceReceiptEvidence) -> None:
        if not isinstance(receipt, SourceReceiptEvidence):
            raise ValueError("receipt must be SourceReceiptEvidence")

        receipts = {item.source_id: item for item in self._read_receipts()}
        current = receipts.get(receipt.source_id)
        if current is not None:
            if receipt.received_at < current.received_at:
                raise ValueError("received_at must not move backwards")
            if receipt.received_at == current.received_at and receipt != current:
                raise ValueError("receipt with the same received_at must match persisted evidence")

        receipts[receipt.source_id] = receipt
        self._write_receipts(tuple(receipts.values()))

    def _read_receipts(self) -> tuple[SourceReceiptEvidence, ...]:
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"source runtime path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SourceRuntimeFormatError(
                "source runtime state must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "source runtime root")
        _require_exact_keys(root, _ROOT_KEYS, "source runtime root")
        schema = _require_string(root["schema"], "source runtime schema")
        if schema != _RUNTIME_SCHEMA:
            raise SourceRuntimeFormatError(f"unsupported source runtime schema: {schema!r}")

        receipts_raw = root["latest_receipts"]
        if not isinstance(receipts_raw, list):
            raise SourceRuntimeFormatError("source runtime latest_receipts must be a JSON array")
        receipts = tuple(
            _parse_receipt(item, index=index) for index, item in enumerate(receipts_raw)
        )
        source_ids = tuple(receipt.source_id for receipt in receipts)
        if len(set(source_ids)) != len(source_ids):
            raise SourceRuntimeFormatError(
                "source runtime contains duplicate receipt source_id values"
            )
        return tuple(sorted(receipts, key=lambda receipt: receipt.source_id))

    def _write_receipts(self, receipts: Sequence[SourceReceiptEvidence]) -> None:
        ordered = tuple(sorted(receipts, key=lambda receipt: receipt.source_id))
        payload = {
            "schema": _RUNTIME_SCHEMA,
            "latest_receipts": [_serialize_receipt(receipt) for receipt in ordered],
        }
        rendered = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

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


def _serialize_receipt(receipt: SourceReceiptEvidence) -> dict[str, object]:
    return {
        "source_id": receipt.source_id,
        "observed_at": (None if receipt.observed_at is None else receipt.observed_at.isoformat()),
        "received_at": receipt.received_at.isoformat(),
    }


def _parse_receipt(value: object, *, index: int) -> SourceReceiptEvidence:
    label = f"source runtime latest_receipts[{index}]"
    receipt = _require_mapping(value, label)
    _require_exact_keys(receipt, _RECEIPT_KEYS, label)
    observed_raw = receipt["observed_at"]
    if observed_raw is not None and not isinstance(observed_raw, str):
        raise SourceRuntimeFormatError(f"{label}.observed_at must be a string or null")
    try:
        return SourceReceiptEvidence(
            source_id=_require_string(receipt["source_id"], f"{label}.source_id"),
            observed_at=(None if observed_raw is None else datetime.fromisoformat(observed_raw)),
            received_at=datetime.fromisoformat(
                _require_string(receipt["received_at"], f"{label}.received_at")
            ),
        )
    except ValueError as error:
        if isinstance(error, SourceRuntimeFormatError):
            raise
        raise SourceRuntimeFormatError(f"{label} is invalid: {error}") from error


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SourceRuntimeFormatError(f"{label} must be a JSON object")
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
        raise SourceRuntimeFormatError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SourceRuntimeFormatError(f"{label} must be a string")
    return value


def _validate_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must not be empty")
    if source_id != source_id.strip():
        raise ValueError("source_id must not contain surrounding whitespace")
