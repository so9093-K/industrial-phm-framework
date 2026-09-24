"""Durable latest runtime evidence for registered operational sources."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from industrial_phm.application.source_receipt import SourceReceiptEvidence

_RUNTIME_SCHEMA_V1 = "industrial-phm-source-runtime-v1"
_RUNTIME_SCHEMA_V2 = "industrial-phm-source-runtime-v2"
_RUNTIME_SCHEMA_V3 = "industrial-phm-source-runtime-v3"
_ROOT_KEYS_V1 = frozenset({"schema", "latest_receipts"})
_ROOT_KEYS_V2 = frozenset({"schema", "latest_receipts", "latest_connection_attempts"})
_ROOT_KEYS_V3 = _ROOT_KEYS_V2
_RECEIPT_KEYS = frozenset({"source_id", "observed_at", "received_at"})
_CONNECTION_ATTEMPT_KEYS_V2 = frozenset(
    {
        "source_id",
        "outcome",
        "attempted_at",
        "connected_at",
        "completed_at",
        "detail",
    }
)
_CONNECTION_ATTEMPT_KEYS_V3 = frozenset(
    {
        "source_id",
        "operation",
        "outcome",
        "attempted_at",
        "connected_at",
        "completed_at",
        "detail",
    }
)


class SourceConnectionAttemptOperation(StrEnum):
    """Operation represented by one bounded connection/session attempt."""

    LEGACY_UNSPECIFIED = "legacy-unspecified"
    OPCUA_READ = "opcua-read"
    OPCUA_SUBSCRIPTION = "opcua-subscription"


class SourceConnectionAttemptOutcome(StrEnum):
    """Outcome of one bounded connector/session attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SourceConnectionAttemptEvidence:
    """Latest bounded connector/session attempt evidence for one source.

    This is historical attempt evidence, not a claim that the source is connected now.
    Operation identifies the producer when known; legacy or caller-created evidence may
    remain LEGACY_UNSPECIFIED rather than being guessed. A successful attempt requires a
    measured connected_at inside the attempted/completed interval. A failed attempt
    requires concrete detail and may not know whether a connection was ever established.
    """

    source_id: str
    outcome: SourceConnectionAttemptOutcome
    attempted_at: datetime
    completed_at: datetime
    connected_at: datetime | None = None
    detail: str | None = None
    operation: SourceConnectionAttemptOperation = (
        SourceConnectionAttemptOperation.LEGACY_UNSPECIFIED
    )

    def __post_init__(self) -> None:
        _validate_source_id(self.source_id)
        if not isinstance(self.operation, SourceConnectionAttemptOperation):
            raise ValueError("operation must be a SourceConnectionAttemptOperation")
        if not isinstance(self.outcome, SourceConnectionAttemptOutcome):
            raise ValueError("outcome must be a SourceConnectionAttemptOutcome")
        _validate_aware_datetime(self.attempted_at, "attempted_at")
        _validate_aware_datetime(self.completed_at, "completed_at")
        if self.completed_at < self.attempted_at:
            raise ValueError("completed_at must not be before attempted_at")

        if self.connected_at is not None:
            _validate_aware_datetime(self.connected_at, "connected_at")
            if self.connected_at < self.attempted_at:
                raise ValueError("connected_at must not be before attempted_at")
            if self.connected_at > self.completed_at:
                raise ValueError("connected_at must not be after completed_at")

        if self.outcome == SourceConnectionAttemptOutcome.SUCCEEDED:
            if self.connected_at is None:
                raise ValueError("succeeded connection attempt requires connected_at")
            if self.detail is not None:
                raise ValueError("succeeded connection attempt must not carry detail")
        else:
            if self.detail is None or not isinstance(self.detail, str) or not self.detail.strip():
                raise ValueError("failed connection attempt requires detail")
            if self.detail != self.detail.strip():
                raise ValueError(
                    "connection attempt detail must not contain surrounding whitespace"
                )


class SourceRuntimeFormatError(ValueError):
    """Raised when persisted source runtime state is unsupported or invalid."""


@runtime_checkable
class SourceRuntimeRepository(Protocol):
    """Persistence boundary for latest receipt and connection-attempt evidence."""

    def get_latest_receipt(self, source_id: str) -> SourceReceiptEvidence | None:
        """Return the latest accepted receipt for one source, if any."""
        ...

    def list_latest_receipts(self) -> tuple[SourceReceiptEvidence, ...]:
        """Return latest receipts in deterministic source-ID order."""
        ...

    def record_receipt(self, receipt: SourceReceiptEvidence) -> None:
        """Persist a latest receipt without allowing received_at regression."""
        ...

    def get_latest_connection_attempt(
        self,
        source_id: str,
    ) -> SourceConnectionAttemptEvidence | None:
        """Return the latest bounded connection/session attempt for one source, if any."""
        ...

    def list_latest_connection_attempts(self) -> tuple[SourceConnectionAttemptEvidence, ...]:
        """Return latest connection attempts in deterministic source-ID order."""
        ...

    def record_connection_attempt(self, attempt: SourceConnectionAttemptEvidence) -> None:
        """Persist latest attempt evidence without allowing completion-time regression."""
        ...


@dataclass(frozen=True, slots=True)
class _SourceRuntimeState:
    receipts: tuple[SourceReceiptEvidence, ...] = ()
    connection_attempts: tuple[SourceConnectionAttemptEvidence, ...] = ()


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
    """Single-writer local JSON repository for latest runtime evidence.

    The repository stays separate from source-registration control-plane state. It stores
    only latest accepted receipt and latest bounded connection-attempt evidence per source;
    it does not store receipt/attempt history, current connection state, retries, buffers,
    throughput, or derived freshness/health assessments.

    Version 1 receipt-only and version 2 operation-less attempt files remain readable.
    V2 attempts are preserved as LEGACY_UNSPECIFIED rather than guessed. Any subsequent
    write persists the version 3 schema while preserving existing evidence.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured runtime-state file path."""
        return self._path

    def get_latest_receipt(self, source_id: str) -> SourceReceiptEvidence | None:
        _validate_source_id(source_id)
        return {receipt.source_id: receipt for receipt in self._read_state().receipts}.get(
            source_id
        )

    def list_latest_receipts(self) -> tuple[SourceReceiptEvidence, ...]:
        return self._read_state().receipts

    def record_receipt(self, receipt: SourceReceiptEvidence) -> None:
        if not isinstance(receipt, SourceReceiptEvidence):
            raise ValueError("receipt must be SourceReceiptEvidence")

        state = self._read_state()
        receipts = {item.source_id: item for item in state.receipts}
        current = receipts.get(receipt.source_id)
        if current is not None:
            if receipt.received_at < current.received_at:
                raise ValueError("received_at must not move backwards")
            if receipt.received_at == current.received_at and receipt != current:
                raise ValueError("receipt with the same received_at must match persisted evidence")

        receipts[receipt.source_id] = receipt
        self._write_state(
            receipts=tuple(receipts.values()),
            connection_attempts=state.connection_attempts,
        )

    def get_latest_connection_attempt(
        self,
        source_id: str,
    ) -> SourceConnectionAttemptEvidence | None:
        _validate_source_id(source_id)
        return {
            attempt.source_id: attempt for attempt in self._read_state().connection_attempts
        }.get(source_id)

    def list_latest_connection_attempts(self) -> tuple[SourceConnectionAttemptEvidence, ...]:
        return self._read_state().connection_attempts

    def record_connection_attempt(self, attempt: SourceConnectionAttemptEvidence) -> None:
        if not isinstance(attempt, SourceConnectionAttemptEvidence):
            raise ValueError("attempt must be SourceConnectionAttemptEvidence")

        state = self._read_state()
        attempts = {item.source_id: item for item in state.connection_attempts}
        current = attempts.get(attempt.source_id)
        if current is not None:
            if attempt.completed_at < current.completed_at:
                raise ValueError("connection attempt completed_at must not move backwards")
            if attempt.completed_at == current.completed_at and attempt != current:
                raise ValueError(
                    "connection attempt with the same completed_at must match persisted evidence"
                )

        attempts[attempt.source_id] = attempt
        self._write_state(
            receipts=state.receipts,
            connection_attempts=tuple(attempts.values()),
        )

    def _read_state(self) -> _SourceRuntimeState:
        if not self._path.exists():
            return _SourceRuntimeState()
        if not self._path.is_file():
            raise OSError(f"source runtime path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SourceRuntimeFormatError(
                "source runtime state must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "source runtime root")
        schema = _require_string(root.get("schema"), "source runtime schema")
        if schema == _RUNTIME_SCHEMA_V1:
            _require_exact_keys(root, _ROOT_KEYS_V1, "source runtime root")
            connection_attempts_raw: object = []
        elif schema == _RUNTIME_SCHEMA_V2:
            _require_exact_keys(root, _ROOT_KEYS_V2, "source runtime root")
            connection_attempts_raw = root["latest_connection_attempts"]
        elif schema == _RUNTIME_SCHEMA_V3:
            _require_exact_keys(root, _ROOT_KEYS_V3, "source runtime root")
            connection_attempts_raw = root["latest_connection_attempts"]
        else:
            raise SourceRuntimeFormatError(f"unsupported source runtime schema: {schema!r}")

        receipts_raw = root["latest_receipts"]
        if not isinstance(receipts_raw, list):
            raise SourceRuntimeFormatError("source runtime latest_receipts must be a JSON array")
        receipts = tuple(
            _parse_receipt(item, index=index) for index, item in enumerate(receipts_raw)
        )
        _reject_duplicate_source_ids(
            tuple(receipt.source_id for receipt in receipts),
            label="receipt",
        )

        if not isinstance(connection_attempts_raw, list):
            raise SourceRuntimeFormatError(
                "source runtime latest_connection_attempts must be a JSON array"
            )
        connection_attempts = tuple(
            _parse_connection_attempt(item, index=index, schema=schema)
            for index, item in enumerate(connection_attempts_raw)
        )
        _reject_duplicate_source_ids(
            tuple(attempt.source_id for attempt in connection_attempts),
            label="connection attempt",
        )

        return _SourceRuntimeState(
            receipts=tuple(sorted(receipts, key=lambda receipt: receipt.source_id)),
            connection_attempts=tuple(
                sorted(connection_attempts, key=lambda attempt: attempt.source_id)
            ),
        )

    def _write_state(
        self,
        *,
        receipts: Sequence[SourceReceiptEvidence],
        connection_attempts: Sequence[SourceConnectionAttemptEvidence],
    ) -> None:
        ordered_receipts = tuple(sorted(receipts, key=lambda receipt: receipt.source_id))
        ordered_attempts = tuple(sorted(connection_attempts, key=lambda attempt: attempt.source_id))
        payload = {
            "schema": _RUNTIME_SCHEMA_V3,
            "latest_connection_attempts": [
                _serialize_connection_attempt(attempt) for attempt in ordered_attempts
            ],
            "latest_receipts": [_serialize_receipt(receipt) for receipt in ordered_receipts],
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


def _serialize_connection_attempt(
    attempt: SourceConnectionAttemptEvidence,
) -> dict[str, object]:
    return {
        "source_id": attempt.source_id,
        "operation": attempt.operation.value,
        "outcome": attempt.outcome.value,
        "attempted_at": attempt.attempted_at.isoformat(),
        "connected_at": (
            None if attempt.connected_at is None else attempt.connected_at.isoformat()
        ),
        "completed_at": attempt.completed_at.isoformat(),
        "detail": attempt.detail,
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


def _parse_connection_attempt(
    value: object,
    *,
    index: int,
    schema: str,
) -> SourceConnectionAttemptEvidence:
    label = f"source runtime latest_connection_attempts[{index}]"
    attempt = _require_mapping(value, label)
    expected_keys = (
        _CONNECTION_ATTEMPT_KEYS_V3
        if schema == _RUNTIME_SCHEMA_V3
        else _CONNECTION_ATTEMPT_KEYS_V2
    )
    _require_exact_keys(attempt, expected_keys, label)
    connected_raw = attempt["connected_at"]
    detail_raw = attempt["detail"]
    if connected_raw is not None and not isinstance(connected_raw, str):
        raise SourceRuntimeFormatError(f"{label}.connected_at must be a string or null")
    if detail_raw is not None and not isinstance(detail_raw, str):
        raise SourceRuntimeFormatError(f"{label}.detail must be a string or null")
    try:
        return SourceConnectionAttemptEvidence(
            source_id=_require_string(attempt["source_id"], f"{label}.source_id"),
            operation=(
                SourceConnectionAttemptOperation.LEGACY_UNSPECIFIED
                if schema == _RUNTIME_SCHEMA_V2
                else SourceConnectionAttemptOperation(
                    _require_string(attempt["operation"], f"{label}.operation")
                )
            ),
            outcome=SourceConnectionAttemptOutcome(
                _require_string(attempt["outcome"], f"{label}.outcome")
            ),
            attempted_at=datetime.fromisoformat(
                _require_string(attempt["attempted_at"], f"{label}.attempted_at")
            ),
            connected_at=(None if connected_raw is None else datetime.fromisoformat(connected_raw)),
            completed_at=datetime.fromisoformat(
                _require_string(attempt["completed_at"], f"{label}.completed_at")
            ),
            detail=detail_raw,
        )
    except ValueError as error:
        if isinstance(error, SourceRuntimeFormatError):
            raise
        raise SourceRuntimeFormatError(f"{label} is invalid: {error}") from error


def _reject_duplicate_source_ids(source_ids: Sequence[str], *, label: str) -> None:
    if len(set(source_ids)) != len(source_ids):
        raise SourceRuntimeFormatError(
            f"source runtime contains duplicate {label} source_id values"
        )


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


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
