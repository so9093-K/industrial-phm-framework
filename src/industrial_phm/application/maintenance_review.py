"""Human review disposition for operational findings."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast
from uuid import uuid4

from industrial_phm.application.operational import OperationalFinding

_FINDING_REVIEW_SCHEMA_V1 = "industrial-phm-finding-review-v1"
_ROOT_KEYS = frozenset({"schema", "events"})
_EVENT_KEYS = frozenset({"event_id", "finding_id", "action", "recorded_at", "note"})


class FindingReviewAction(StrEnum):
    """Explicit human actions in the finding-review workflow."""

    NOTE = "note"
    ACKNOWLEDGE = "acknowledge"
    CLOSE = "close"


class FindingReviewStatus(StrEnum):
    """Derived current review status for one finding."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class FindingReviewEvent:
    """One append-only human review action linked to an OperationalFinding."""

    event_id: str
    finding_id: str
    action: FindingReviewAction
    recorded_at: datetime
    note: str = ""

    def __post_init__(self) -> None:
        _validate_identifier(self.event_id, "event_id")
        _validate_identifier(self.finding_id, "finding_id")
        if not isinstance(self.action, FindingReviewAction):
            raise ValueError("action must be a FindingReviewAction")
        if not isinstance(self.recorded_at, datetime) or self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be a timezone-aware datetime")
        if not isinstance(self.note, str):
            raise ValueError("note must be a string")
        if self.note != self.note.strip():
            raise ValueError("note must not contain surrounding whitespace")
        if self.action == FindingReviewAction.NOTE and not self.note:
            raise ValueError("note action requires non-empty note text")


class FindingReviewHistoryFormatError(ValueError):
    """Raised when persisted finding-review state is invalid."""


def create_finding_review_event(
    finding: OperationalFinding,
    *,
    action: FindingReviewAction,
    note: str = "",
    clock: callable | None = None,
) -> FindingReviewEvent:
    """Create one explicit human review event for an existing finding."""
    if not isinstance(finding, OperationalFinding):
        raise ValueError("finding must be OperationalFinding")
    if not isinstance(action, FindingReviewAction):
        raise ValueError("action must be a FindingReviewAction")
    now = datetime.now(UTC) if clock is None else clock()
    return FindingReviewEvent(
        event_id=f"finding-review-event-{uuid4()}",
        finding_id=finding.finding_id,
        action=action,
        recorded_at=now,
        note=note.strip(),
    )


def finding_review_status(
    events: Sequence[FindingReviewEvent],
    finding_id: str,
) -> FindingReviewStatus:
    """Derive current review status while validating allowed transitions."""
    _validate_identifier(finding_id, "finding_id")
    status = FindingReviewStatus.OPEN
    for event in events:
        if not isinstance(event, FindingReviewEvent):
            raise ValueError("events must contain only FindingReviewEvent values")
        if event.finding_id != finding_id:
            continue
        if status == FindingReviewStatus.CLOSED:
            raise ValueError("closed finding review cannot accept additional events")
        if event.action == FindingReviewAction.NOTE:
            continue
        if event.action == FindingReviewAction.ACKNOWLEDGE:
            if status != FindingReviewStatus.OPEN:
                raise ValueError("finding review can only be acknowledged from OPEN")
            status = FindingReviewStatus.ACKNOWLEDGED
            continue
        if event.action == FindingReviewAction.CLOSE:
            if status != FindingReviewStatus.ACKNOWLEDGED:
                raise ValueError("finding review can only be closed from ACKNOWLEDGED")
            status = FindingReviewStatus.CLOSED
            continue
        raise AssertionError(f"unsupported finding review action: {event.action!r}")
    return status


class JsonFindingReviewRepository:
    """Append-only local review-event repository with transition validation."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured review-event path."""
        return self._path

    def list_events(self) -> tuple[FindingReviewEvent, ...]:
        """Return review events in persisted append order."""
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"finding review state path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise FindingReviewHistoryFormatError(
                "finding review state must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "finding review root")
        _require_exact_keys(root, _ROOT_KEYS, "finding review root")
        schema = _require_string(root["schema"], "finding review schema")
        if schema != _FINDING_REVIEW_SCHEMA_V1:
            raise FindingReviewHistoryFormatError(
                f"unsupported finding review schema: {schema!r}"
            )

        events_raw = root["events"]
        if not isinstance(events_raw, list):
            raise FindingReviewHistoryFormatError(
                "finding review events must be a JSON array"
            )
        events = tuple(
            _parse_event(value, index=index) for index, value in enumerate(events_raw)
        )
        event_ids = tuple(event.event_id for event in events)
        if len(set(event_ids)) != len(event_ids):
            raise FindingReviewHistoryFormatError(
                "finding review state contains duplicate event_id values"
            )

        finding_ids = tuple(dict.fromkeys(event.finding_id for event in events))
        try:
            for finding_id in finding_ids:
                finding_review_status(events, finding_id)
        except ValueError as error:
            raise FindingReviewHistoryFormatError(
                f"finding review state contains invalid transitions: {error}"
            ) from error
        return events

    def record(self, event: FindingReviewEvent) -> None:
        """Append one event after validating time ordering and state transition."""
        if not isinstance(event, FindingReviewEvent):
            raise ValueError("event must be FindingReviewEvent")

        events = self.list_events()
        current = next(
            (item for item in events if item.event_id == event.event_id),
            None,
        )
        if current is not None:
            if current != event:
                raise ValueError("event_id already exists with different persisted review data")
            return

        same_finding = tuple(item for item in events if item.finding_id == event.finding_id)
        if same_finding and event.recorded_at < same_finding[-1].recorded_at:
            raise ValueError("recorded_at must not move backwards for one finding review")

        candidate = (*events, event)
        finding_review_status(candidate, event.finding_id)
        self._write(candidate)

    def status_for(self, finding_id: str) -> FindingReviewStatus:
        """Return current derived review status for one finding."""
        return finding_review_status(self.list_events(), finding_id)

    def _write(self, events: Sequence[FindingReviewEvent]) -> None:
        payload = {
            "schema": _FINDING_REVIEW_SCHEMA_V1,
            "events": [_serialize_event(event) for event in events],
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


def _serialize_event(event: FindingReviewEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "finding_id": event.finding_id,
        "action": event.action.value,
        "recorded_at": event.recorded_at.isoformat(),
        "note": event.note,
    }


def _parse_event(value: object, *, index: int) -> FindingReviewEvent:
    label = f"finding review events[{index}]"
    raw = _require_mapping(value, label)
    _require_exact_keys(raw, _EVENT_KEYS, label)
    try:
        return FindingReviewEvent(
            event_id=_require_string(raw["event_id"], f"{label}.event_id"),
            finding_id=_require_string(raw["finding_id"], f"{label}.finding_id"),
            action=FindingReviewAction(
                _require_string(raw["action"], f"{label}.action")
            ),
            recorded_at=_require_datetime(
                raw["recorded_at"], f"{label}.recorded_at"
            ),
            note=_require_string(raw["note"], f"{label}.note"),
        )
    except ValueError as error:
        if isinstance(error, FindingReviewHistoryFormatError):
            raise
        raise FindingReviewHistoryFormatError(f"{label} is invalid: {error}") from error


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise FindingReviewHistoryFormatError(f"{label} must be a JSON object")
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
        raise FindingReviewHistoryFormatError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise FindingReviewHistoryFormatError(f"{label} must be a string")
    return value


def _require_datetime(value: object, label: str) -> datetime:
    raw = _require_string(value, label)
    try:
        result = datetime.fromisoformat(raw)
    except ValueError as error:
        raise FindingReviewHistoryFormatError(
            f"{label} must be an ISO 8601 datetime"
        ) from error
    if result.utcoffset() is None:
        raise FindingReviewHistoryFormatError(f"{label} must be timezone-aware")
    return result


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
