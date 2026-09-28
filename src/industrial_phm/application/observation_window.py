"""Bounded event-time observation window assembly and durable finalized history.

This module is a reference runtime boundary, not a streaming framework. Callers own the
watermark policy and explicit window range. The in-memory buffer is intentionally bounded
and non-durable; only finalized windows are persisted by the JSON repository.

A COMPLETE window means every expected channel contributed at least one accepted event.
It does not mean synchronized sampling, equal event counts, gap-free delivery, exactly-once
delivery, valid asset condition, or analysis readiness.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaPersistentDataChangeEvent,
)
from industrial_phm.application.source_subscription import (
    RegisteredOpcUaDataChangeEvent,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)

_WINDOW_SCHEMA = "industrial-phm-observation-window-v1"
_ROOT_KEYS = frozenset({"schema", "windows"})
_WINDOW_KEYS = frozenset(
    {
        "window_id",
        "source_id",
        "asset_id",
        "measurement_point_id",
        "window_start",
        "window_end",
        "watermark_at_close",
        "finalized_at",
        "expected_channel_ids",
        "events",
        "out_of_order_accepted_count",
        "late_rejected_count",
        "duplicate_rejected_count",
        "timing_unavailable_rejected_count",
        "unexpected_channel_rejected_count",
        "outside_window_rejected_count",
        "buffer_full_rejected_count",
        "future_timestamp_rejected_count",
    }
)
_PERSISTENT_EVENT_KEYS = frozenset(
    {
        "connection_epoch",
        "event_index",
        "registered_event",
        "event_time",
    }
)
_REGISTERED_EVENT_KEYS = frozenset(
    {
        "source_id",
        "asset_id",
        "endpoint_url",
        "measurement_point_id",
        "collection_index",
        "notification",
    }
)
_NOTIFICATION_KEYS = frozenset({"replayed", "observation"})
_OBSERVATION_KEYS = frozenset(
    {
        "channel_id",
        "node_id",
        "value",
        "status_code",
        "status_good",
        "status_text",
        "variant_type",
        "source_timestamp",
        "server_timestamp",
        "received_at",
    }
)
_EVENT_TIME_KEYS = frozenset(
    {
        "basis",
        "source_timestamp",
        "server_timestamp",
        "received_at",
        "ingested_at",
        "event_at",
    }
)


class ObservationWindowEventDisposition(StrEnum):
    """Factual outcome of presenting one delivery to the bounded window.

    DUPLICATE means the same platform-local delivery identity was presented again.
    It does not deduplicate replayed protocol values that arrive with a new epoch/index.
    """

    IN_ORDER = "IN_ORDER"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    LATE = "LATE"
    DUPLICATE = "DUPLICATE"
    TIMING_UNAVAILABLE = "TIMING_UNAVAILABLE"
    UNEXPECTED_CHANNEL = "UNEXPECTED_CHANNEL"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    BUFFER_FULL = "BUFFER_FULL"


class ObservationWindowCompleteness(StrEnum):
    """Configured-channel coverage at finalized-window scope."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True, slots=True)
class ObservationWindowIngestResult:
    """Disposition and timing context for one local delivery attempt."""

    disposition: ObservationWindowEventDisposition
    local_delivery_identity: tuple[str, int, int]
    event_at: datetime | None
    watermark_at_ingest: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ObservationWindowEventDisposition):
            raise ValueError("disposition must be ObservationWindowEventDisposition")
        _validate_local_delivery_identity(self.local_delivery_identity)
        if self.event_at is not None:
            _validate_aware_datetime(self.event_at, "event_at")
        if self.watermark_at_ingest is not None:
            _validate_aware_datetime(self.watermark_at_ingest, "watermark_at_ingest")

    @property
    def accepted(self) -> bool:
        """Return whether the event payload entered the bounded window buffer."""
        return self.disposition in {
            ObservationWindowEventDisposition.IN_ORDER,
            ObservationWindowEventDisposition.OUT_OF_ORDER,
        }


@dataclass(frozen=True, slots=True)
class DurableObservationWindow:
    """Finalized event-time window with accepted-event and rejection evidence."""

    window_id: str
    source_id: str
    asset_id: str
    window_start: datetime
    window_end: datetime
    watermark_at_close: datetime
    finalized_at: datetime
    expected_channel_ids: Sequence[str]
    events: Sequence[OpcUaPersistentDataChangeEvent]
    measurement_point_id: str | None = None
    out_of_order_accepted_count: int = 0
    late_rejected_count: int = 0
    duplicate_rejected_count: int = 0
    timing_unavailable_rejected_count: int = 0
    unexpected_channel_rejected_count: int = 0
    outside_window_rejected_count: int = 0
    future_timestamp_rejected_count: int = 0
    buffer_full_rejected_count: int = 0

    def __post_init__(self) -> None:
        _validate_identifier(self.window_id, "window_id")
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.asset_id, "asset_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")

        _validate_aware_datetime(self.window_start, "window_start")
        _validate_aware_datetime(self.window_end, "window_end")
        _validate_aware_datetime(self.watermark_at_close, "watermark_at_close")
        _validate_aware_datetime(self.finalized_at, "finalized_at")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        if self.watermark_at_close < self.window_end:
            raise ValueError("watermark_at_close must reach or pass window_end")

        expected = tuple(self.expected_channel_ids)
        _validate_channel_ids(expected, "expected_channel_ids")
        if not expected:
            raise ValueError("expected_channel_ids must not be empty")

        events = tuple(self.events)
        if any(not isinstance(item, OpcUaPersistentDataChangeEvent) for item in events):
            raise ValueError("events must contain only OpcUaPersistentDataChangeEvent values")
        identities = tuple(item.local_delivery_identity for item in events)
        if len(set(identities)) != len(identities):
            raise ValueError("events must contain unique local delivery identities")
        if tuple(sorted(events, key=_accepted_event_sort_key)) != events:
            raise ValueError("events must use deterministic event-time ordering")

        expected_set = set(expected)
        latest_ingested_at: datetime | None = None
        for event in events:
            registered = event.event
            if registered.source_id != self.source_id:
                raise ValueError("window event source_id must match window source_id")
            if registered.asset_id != self.asset_id:
                raise ValueError("window event asset_id must match window asset_id")
            if registered.measurement_point_id != self.measurement_point_id:
                raise ValueError(
                    "window event measurement_point_id must match window measurement_point_id"
                )
            if event.channel_id not in expected_set:
                raise ValueError("window event channel_id must be expected")
            event_at = event.event_time.event_at
            if event_at is None:
                raise ValueError("durable window event requires event time")
            if not self.window_start <= event_at < self.window_end:
                raise ValueError("durable window event must fall inside [window_start, window_end)")
            if latest_ingested_at is None or event.event_time.ingested_at > latest_ingested_at:
                latest_ingested_at = event.event_time.ingested_at

        if latest_ingested_at is not None and self.finalized_at < latest_ingested_at:
            raise ValueError("finalized_at must not be before accepted event ingestion")

        for field_name in (
            "out_of_order_accepted_count",
            "late_rejected_count",
            "duplicate_rejected_count",
            "timing_unavailable_rejected_count",
            "unexpected_channel_rejected_count",
            "outside_window_rejected_count",
            "future_timestamp_rejected_count",
            "buffer_full_rejected_count",
        ):
            _validate_non_negative_int(getattr(self, field_name), field_name)

        object.__setattr__(self, "expected_channel_ids", expected)
        object.__setattr__(self, "events", events)

    @property
    def observed_channel_ids(self) -> tuple[str, ...]:
        """Return accepted channel coverage in expected-channel order."""
        observed = {event.channel_id for event in self.events}
        return tuple(
            channel_id for channel_id in self.expected_channel_ids if channel_id in observed
        )

    @property
    def missing_channel_ids(self) -> tuple[str, ...]:
        """Return expected channels with no accepted event in this finalized window."""
        observed = set(self.observed_channel_ids)
        return tuple(
            channel_id for channel_id in self.expected_channel_ids if channel_id not in observed
        )

    @property
    def completeness(self) -> ObservationWindowCompleteness:
        """Return configured-channel coverage only, not analysis readiness."""
        if self.missing_channel_ids:
            return ObservationWindowCompleteness.PARTIAL
        return ObservationWindowCompleteness.COMPLETE

    @property
    def accepted_event_count(self) -> int:
        return len(self.events)

    @property
    def rejected_event_count(self) -> int:
        return (
            self.late_rejected_count
            + self.duplicate_rejected_count
            + self.timing_unavailable_rejected_count
            + self.unexpected_channel_rejected_count
            + self.outside_window_rejected_count
            + self.future_timestamp_rejected_count
            + self.buffer_full_rejected_count
        )


class ObservationWindowBuffer:
    """Bounded, non-durable reference assembler for one explicit event-time window."""

    def __init__(
        self,
        *,
        window_id: str,
        source_id: str,
        asset_id: str,
        expected_channel_ids: Sequence[str],
        window_start: datetime,
        window_end: datetime,
        max_buffered_events: int,
        max_future_skew_seconds: float,
        measurement_point_id: str | None = None,
    ) -> None:
        _validate_identifier(window_id, "window_id")
        _validate_identifier(source_id, "source_id")
        _validate_identifier(asset_id, "asset_id")
        if measurement_point_id is not None:
            _validate_identifier(measurement_point_id, "measurement_point_id")
        expected = tuple(expected_channel_ids)
        _validate_channel_ids(expected, "expected_channel_ids")
        if not expected:
            raise ValueError("expected_channel_ids must not be empty")
        _validate_aware_datetime(window_start, "window_start")
        _validate_aware_datetime(window_end, "window_end")
        if window_end <= window_start:
            raise ValueError("window_end must be after window_start")
        if isinstance(max_buffered_events, bool) or not isinstance(
            max_buffered_events,
            int,
        ):
            raise ValueError("max_buffered_events must be an integer")
        if max_buffered_events < 1:
            raise ValueError("max_buffered_events must be at least 1")
        _validate_non_negative_finite(
            max_future_skew_seconds,
            "max_future_skew_seconds",
        )

        self._window_id = window_id
        self._source_id = source_id
        self._asset_id = asset_id
        self._measurement_point_id = measurement_point_id
        self._expected_channel_ids = expected
        self._expected_channel_set = set(expected)
        self._window_start = window_start
        self._window_end = window_end
        self._max_buffered_events = max_buffered_events
        self._max_future_skew_seconds = float(max_future_skew_seconds)
        self._watermark: datetime | None = None
        self._max_accepted_event_at: datetime | None = None
        self._events: list[OpcUaPersistentDataChangeEvent] = []
        self._seen_delivery_identities: set[tuple[str, int, int]] = set()
        self._out_of_order_accepted_count = 0
        self._late_rejected_count = 0
        self._duplicate_rejected_count = 0
        self._timing_unavailable_rejected_count = 0
        self._unexpected_channel_rejected_count = 0
        self._outside_window_rejected_count = 0
        self._future_timestamp_rejected_count = 0
        self._buffer_full_rejected_count = 0
        self._finalized = False

    @property
    def watermark(self) -> datetime | None:
        return self._watermark

    @property
    def buffered_event_count(self) -> int:
        return len(self._events)

    def advance_watermark(self, watermark: datetime) -> None:
        """Advance caller-owned event-time progress monotonically."""
        if self._finalized:
            raise ValueError("finalized window buffer cannot advance watermark")
        _validate_aware_datetime(watermark, "watermark")
        if self._watermark is not None and watermark < self._watermark:
            raise ValueError("watermark must not move backwards")
        self._watermark = watermark

    def ingest(
        self,
        event: OpcUaPersistentDataChangeEvent,
    ) -> ObservationWindowIngestResult:
        """Classify and optionally accept one persistent DataChange delivery."""
        if self._finalized:
            raise ValueError("finalized window buffer cannot ingest events")
        if not isinstance(event, OpcUaPersistentDataChangeEvent):
            raise ValueError("event must be an OpcUaPersistentDataChangeEvent")

        registered = event.event
        if registered.source_id != self._source_id:
            raise ValueError("event source_id must match window source_id")
        if registered.asset_id != self._asset_id:
            raise ValueError("event asset_id must match window asset_id")
        if registered.measurement_point_id != self._measurement_point_id:
            raise ValueError("event measurement_point_id must match window measurement_point_id")

        identity = event.local_delivery_identity
        event_at = event.event_time.event_at
        if identity in self._seen_delivery_identities:
            self._duplicate_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.DUPLICATE,
                identity,
                event_at,
            )
        self._seen_delivery_identities.add(identity)

        if event_at is None:
            self._timing_unavailable_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.TIMING_UNAVAILABLE,
                identity,
                None,
            )

        if event.channel_id not in self._expected_channel_set:
            self._unexpected_channel_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.UNEXPECTED_CHANNEL,
                identity,
                event_at,
            )

        if not self._window_start <= event_at < self._window_end:
            self._outside_window_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.OUTSIDE_WINDOW,
                identity,
                event_at,
            )

        future_skew_seconds = (event_at - event.event_time.ingested_at).total_seconds()
        if future_skew_seconds > self._max_future_skew_seconds:
            self._future_timestamp_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.FUTURE_TIMESTAMP,
                identity,
                event_at,
            )

        if self._watermark is not None and event_at < self._watermark:
            self._late_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.LATE,
                identity,
                event_at,
            )

        if len(self._events) >= self._max_buffered_events:
            self._buffer_full_rejected_count += 1
            return self._result(
                ObservationWindowEventDisposition.BUFFER_FULL,
                identity,
                event_at,
            )

        disposition = ObservationWindowEventDisposition.IN_ORDER
        if self._max_accepted_event_at is not None and event_at < self._max_accepted_event_at:
            disposition = ObservationWindowEventDisposition.OUT_OF_ORDER
            self._out_of_order_accepted_count += 1

        self._events.append(event)
        if self._max_accepted_event_at is None or event_at > self._max_accepted_event_at:
            self._max_accepted_event_at = event_at
        return self._result(disposition, identity, event_at)

    def finalize(self, *, finalized_at: datetime) -> DurableObservationWindow:
        """Finalize only after caller watermark reaches the explicit window end."""
        if self._finalized:
            raise ValueError("window buffer has already been finalized")
        _validate_aware_datetime(finalized_at, "finalized_at")
        if self._watermark is None or self._watermark < self._window_end:
            raise ValueError("watermark must reach or pass window_end before finalization")

        window = DurableObservationWindow(
            window_id=self._window_id,
            source_id=self._source_id,
            asset_id=self._asset_id,
            measurement_point_id=self._measurement_point_id,
            window_start=self._window_start,
            window_end=self._window_end,
            watermark_at_close=self._watermark,
            finalized_at=finalized_at,
            expected_channel_ids=self._expected_channel_ids,
            events=tuple(sorted(self._events, key=_accepted_event_sort_key)),
            out_of_order_accepted_count=self._out_of_order_accepted_count,
            late_rejected_count=self._late_rejected_count,
            duplicate_rejected_count=self._duplicate_rejected_count,
            timing_unavailable_rejected_count=self._timing_unavailable_rejected_count,
            unexpected_channel_rejected_count=self._unexpected_channel_rejected_count,
            outside_window_rejected_count=self._outside_window_rejected_count,
            future_timestamp_rejected_count=self._future_timestamp_rejected_count,
            buffer_full_rejected_count=self._buffer_full_rejected_count,
        )
        self._finalized = True
        return window

    def _result(
        self,
        disposition: ObservationWindowEventDisposition,
        identity: tuple[str, int, int],
        event_at: datetime | None,
    ) -> ObservationWindowIngestResult:
        return ObservationWindowIngestResult(
            disposition=disposition,
            local_delivery_identity=identity,
            event_at=event_at,
            watermark_at_ingest=self._watermark,
        )


class ObservationWindowFormatError(ValueError):
    """Raised when durable observation-window state is unsupported or malformed."""


@runtime_checkable
class ObservationWindowRepository(Protocol):
    """Persistence boundary for finalized observation windows."""

    def get(self, window_id: str) -> DurableObservationWindow:
        """Return one finalized window or raise KeyError when absent."""
        ...

    def list_windows(self) -> tuple[DurableObservationWindow, ...]:
        """Return finalized windows in deterministic source/time/id order."""
        ...

    def record_window(self, window: DurableObservationWindow) -> None:
        """Persist a finalized window idempotently and reject identity conflicts."""
        ...


class JsonObservationWindowRepository:
    """Single-writer local JSON history for finalized observation windows only."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def get(self, window_id: str) -> DurableObservationWindow:
        _validate_identifier(window_id, "window_id")
        windows = {item.window_id: item for item in self._read_windows()}
        try:
            return windows[window_id]
        except KeyError as error:
            raise KeyError(f"observation window does not exist: {window_id}") from error

    def list_windows(self) -> tuple[DurableObservationWindow, ...]:
        return self._read_windows()

    def record_window(self, window: DurableObservationWindow) -> None:
        if not isinstance(window, DurableObservationWindow):
            raise ValueError("window must be DurableObservationWindow")

        windows = {item.window_id: item for item in self._read_windows()}
        current = windows.get(window.window_id)
        if current is not None:
            if current != window:
                raise ValueError(
                    "observation window with the same window_id must match persisted evidence"
                )
            return

        new_identities = {event.local_delivery_identity for event in window.events}
        for existing in windows.values():
            if existing.source_id != window.source_id:
                continue
            existing_identities = {event.local_delivery_identity for event in existing.events}
            overlap = new_identities & existing_identities
            if overlap:
                raise ValueError(
                    "local delivery identity must not be persisted in multiple windows "
                    f"for one source: {sorted(overlap)!r}"
                )

        windows[window.window_id] = window
        self._write_windows(tuple(windows.values()))

    def _read_windows(self) -> tuple[DurableObservationWindow, ...]:
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"observation-window path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ObservationWindowFormatError(
                "observation-window state must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "observation-window root")
        _require_exact_keys(root, _ROOT_KEYS, "observation-window root")
        schema = _require_string(root["schema"], "observation-window schema")
        if schema != _WINDOW_SCHEMA:
            raise ObservationWindowFormatError(f"unsupported observation-window schema: {schema!r}")

        raw_windows = root["windows"]
        if not isinstance(raw_windows, list):
            raise ObservationWindowFormatError("observation-window windows must be a JSON array")
        windows = tuple(_parse_window(item, index=index) for index, item in enumerate(raw_windows))
        ids = tuple(item.window_id for item in windows)
        if len(set(ids)) != len(ids):
            raise ObservationWindowFormatError("observation-window window_id values must be unique")

        delivery_owners: dict[tuple[str, tuple[str, int, int]], str] = {}
        for window in windows:
            for event in window.events:
                key = (window.source_id, event.local_delivery_identity)
                previous = delivery_owners.get(key)
                if previous is not None and previous != window.window_id:
                    raise ObservationWindowFormatError(
                        "local delivery identity appears in multiple persisted windows"
                    )
                delivery_owners[key] = window.window_id

        return tuple(sorted(windows, key=_window_sort_key))

    def _write_windows(
        self,
        windows: Sequence[DurableObservationWindow],
    ) -> None:
        ordered = tuple(sorted(windows, key=_window_sort_key))
        payload = {
            "schema": _WINDOW_SCHEMA,
            "windows": [_serialize_window(window) for window in ordered],
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


def _accepted_event_sort_key(
    event: OpcUaPersistentDataChangeEvent,
) -> tuple[datetime, int, int, str]:
    event_at = event.event_time.event_at
    if event_at is None:
        raise ValueError("accepted event must have event time")
    return event_at, event.connection_epoch, event.event_index, event.channel_id


def _window_sort_key(window: DurableObservationWindow) -> tuple[str, datetime, str]:
    return window.source_id, window.window_start, window.window_id


def _serialize_window(window: DurableObservationWindow) -> dict[str, object]:
    return {
        "window_id": window.window_id,
        "source_id": window.source_id,
        "asset_id": window.asset_id,
        "measurement_point_id": window.measurement_point_id,
        "window_start": window.window_start.isoformat(),
        "window_end": window.window_end.isoformat(),
        "watermark_at_close": window.watermark_at_close.isoformat(),
        "finalized_at": window.finalized_at.isoformat(),
        "expected_channel_ids": list(window.expected_channel_ids),
        "events": [_serialize_persistent_event(event) for event in window.events],
        "out_of_order_accepted_count": window.out_of_order_accepted_count,
        "late_rejected_count": window.late_rejected_count,
        "duplicate_rejected_count": window.duplicate_rejected_count,
        "timing_unavailable_rejected_count": window.timing_unavailable_rejected_count,
        "unexpected_channel_rejected_count": window.unexpected_channel_rejected_count,
        "outside_window_rejected_count": window.outside_window_rejected_count,
        "future_timestamp_rejected_count": window.future_timestamp_rejected_count,
        "buffer_full_rejected_count": window.buffer_full_rejected_count,
    }


def _serialize_persistent_event(
    event: OpcUaPersistentDataChangeEvent,
) -> dict[str, object]:
    registered = event.event
    notification = registered.notification
    observation = notification.observation
    timing = event.event_time
    return {
        "connection_epoch": event.connection_epoch,
        "event_index": event.event_index,
        "registered_event": {
            "source_id": registered.source_id,
            "asset_id": registered.asset_id,
            "endpoint_url": registered.endpoint_url,
            "measurement_point_id": registered.measurement_point_id,
            "collection_index": registered.collection_index,
            "notification": {
                "replayed": notification.replayed,
                "observation": {
                    "channel_id": observation.channel_id,
                    "node_id": observation.node_id,
                    "value": observation.value,
                    "status_code": observation.status_code,
                    "status_good": observation.status_good,
                    "status_text": observation.status_text,
                    "variant_type": observation.variant_type,
                    "source_timestamp": _serialize_optional_datetime(observation.source_timestamp),
                    "server_timestamp": _serialize_optional_datetime(observation.server_timestamp),
                    "received_at": observation.received_at.isoformat(),
                },
            },
        },
        "event_time": {
            "basis": timing.basis.value,
            "source_timestamp": _serialize_optional_datetime(timing.source_timestamp),
            "server_timestamp": _serialize_optional_datetime(timing.server_timestamp),
            "received_at": timing.received_at.isoformat(),
            "ingested_at": timing.ingested_at.isoformat(),
            "event_at": _serialize_optional_datetime(timing.event_at),
        },
    }


def _parse_window(raw: object, *, index: int) -> DurableObservationWindow:
    context = f"observation-window windows[{index}]"
    item = _require_mapping(raw, context)
    _require_exact_keys(item, _WINDOW_KEYS, context)

    expected_raw = item["expected_channel_ids"]
    if not isinstance(expected_raw, list):
        raise ObservationWindowFormatError(f"{context}.expected_channel_ids must be a JSON array")
    expected = tuple(
        _require_string(value, f"{context}.expected_channel_ids[{item_index}]")
        for item_index, value in enumerate(expected_raw)
    )

    events_raw = item["events"]
    if not isinstance(events_raw, list):
        raise ObservationWindowFormatError(f"{context}.events must be a JSON array")
    events = tuple(
        _parse_persistent_event(value, context=f"{context}.events[{event_index}]")
        for event_index, value in enumerate(events_raw)
    )

    try:
        return DurableObservationWindow(
            window_id=_require_string(item["window_id"], f"{context}.window_id"),
            source_id=_require_string(item["source_id"], f"{context}.source_id"),
            asset_id=_require_string(item["asset_id"], f"{context}.asset_id"),
            measurement_point_id=_require_optional_string(
                item["measurement_point_id"],
                f"{context}.measurement_point_id",
            ),
            window_start=_require_datetime(item["window_start"], f"{context}.window_start"),
            window_end=_require_datetime(item["window_end"], f"{context}.window_end"),
            watermark_at_close=_require_datetime(
                item["watermark_at_close"],
                f"{context}.watermark_at_close",
            ),
            finalized_at=_require_datetime(
                item["finalized_at"],
                f"{context}.finalized_at",
            ),
            expected_channel_ids=expected,
            events=events,
            out_of_order_accepted_count=_require_non_negative_int(
                item["out_of_order_accepted_count"],
                f"{context}.out_of_order_accepted_count",
            ),
            late_rejected_count=_require_non_negative_int(
                item["late_rejected_count"],
                f"{context}.late_rejected_count",
            ),
            duplicate_rejected_count=_require_non_negative_int(
                item["duplicate_rejected_count"],
                f"{context}.duplicate_rejected_count",
            ),
            timing_unavailable_rejected_count=_require_non_negative_int(
                item["timing_unavailable_rejected_count"],
                f"{context}.timing_unavailable_rejected_count",
            ),
            unexpected_channel_rejected_count=_require_non_negative_int(
                item["unexpected_channel_rejected_count"],
                f"{context}.unexpected_channel_rejected_count",
            ),
            outside_window_rejected_count=_require_non_negative_int(
                item["outside_window_rejected_count"],
                f"{context}.outside_window_rejected_count",
            ),
            future_timestamp_rejected_count=_require_non_negative_int(
                item["future_timestamp_rejected_count"],
                f"{context}.future_timestamp_rejected_count",
            ),
            buffer_full_rejected_count=_require_non_negative_int(
                item["buffer_full_rejected_count"],
                f"{context}.buffer_full_rejected_count",
            ),
        )
    except ValueError as error:
        raise ObservationWindowFormatError(f"{context} is invalid: {error}") from error


def _parse_persistent_event(
    raw: object,
    *,
    context: str,
) -> OpcUaPersistentDataChangeEvent:
    item = _require_mapping(raw, context)
    _require_exact_keys(item, _PERSISTENT_EVENT_KEYS, context)

    registered_raw = _require_mapping(
        item["registered_event"],
        f"{context}.registered_event",
    )
    _require_exact_keys(
        registered_raw,
        _REGISTERED_EVENT_KEYS,
        f"{context}.registered_event",
    )
    notification_raw = _require_mapping(
        registered_raw["notification"],
        f"{context}.registered_event.notification",
    )
    _require_exact_keys(
        notification_raw,
        _NOTIFICATION_KEYS,
        f"{context}.registered_event.notification",
    )
    observation_raw = _require_mapping(
        notification_raw["observation"],
        f"{context}.registered_event.notification.observation",
    )
    _require_exact_keys(
        observation_raw,
        _OBSERVATION_KEYS,
        f"{context}.registered_event.notification.observation",
    )

    event_time_raw = _require_mapping(item["event_time"], f"{context}.event_time")
    _require_exact_keys(event_time_raw, _EVENT_TIME_KEYS, f"{context}.event_time")

    try:
        observation = OpcUaNodeObservation(
            channel_id=_require_string(
                observation_raw["channel_id"],
                f"{context}.observation.channel_id",
            ),
            node_id=_require_string(
                observation_raw["node_id"],
                f"{context}.observation.node_id",
            ),
            value=_require_optional_float(
                observation_raw["value"],
                f"{context}.observation.value",
            ),
            status_code=_require_int(
                observation_raw["status_code"],
                f"{context}.observation.status_code",
            ),
            status_good=_require_bool(
                observation_raw["status_good"],
                f"{context}.observation.status_good",
            ),
            status_text=_require_string(
                observation_raw["status_text"],
                f"{context}.observation.status_text",
            ),
            variant_type=_require_optional_string(
                observation_raw["variant_type"],
                f"{context}.observation.variant_type",
            ),
            source_timestamp=_require_optional_datetime(
                observation_raw["source_timestamp"],
                f"{context}.observation.source_timestamp",
            ),
            server_timestamp=_require_optional_datetime(
                observation_raw["server_timestamp"],
                f"{context}.observation.server_timestamp",
            ),
            received_at=_require_datetime(
                observation_raw["received_at"],
                f"{context}.observation.received_at",
            ),
        )
        notification = OpcUaSubscriptionNotification(
            observation=observation,
            replayed=_require_bool(
                notification_raw["replayed"],
                f"{context}.notification.replayed",
            ),
        )
        registered = RegisteredOpcUaDataChangeEvent(
            source_id=_require_string(
                registered_raw["source_id"],
                f"{context}.registered_event.source_id",
            ),
            asset_id=_require_string(
                registered_raw["asset_id"],
                f"{context}.registered_event.asset_id",
            ),
            endpoint_url=_require_string(
                registered_raw["endpoint_url"],
                f"{context}.registered_event.endpoint_url",
            ),
            measurement_point_id=_require_optional_string(
                registered_raw["measurement_point_id"],
                f"{context}.registered_event.measurement_point_id",
            ),
            collection_index=_require_non_negative_int(
                registered_raw["collection_index"],
                f"{context}.registered_event.collection_index",
            ),
            notification=notification,
        )
        try:
            basis = OpcUaEventTimeBasis(
                _require_string(
                    event_time_raw["basis"],
                    f"{context}.event_time.basis",
                )
            )
        except ValueError as error:
            raise ObservationWindowFormatError(
                f"{context}.event_time.basis is unsupported"
            ) from error

        event_time = OpcUaEventTimeEvidence(
            basis=basis,
            source_timestamp=_require_optional_datetime(
                event_time_raw["source_timestamp"],
                f"{context}.event_time.source_timestamp",
            ),
            server_timestamp=_require_optional_datetime(
                event_time_raw["server_timestamp"],
                f"{context}.event_time.server_timestamp",
            ),
            received_at=_require_datetime(
                event_time_raw["received_at"],
                f"{context}.event_time.received_at",
            ),
            ingested_at=_require_datetime(
                event_time_raw["ingested_at"],
                f"{context}.event_time.ingested_at",
            ),
            event_at=_require_optional_datetime(
                event_time_raw["event_at"],
                f"{context}.event_time.event_at",
            ),
        )
        return OpcUaPersistentDataChangeEvent(
            event=registered,
            connection_epoch=_require_positive_int(
                item["connection_epoch"],
                f"{context}.connection_epoch",
            ),
            event_index=_require_non_negative_int(
                item["event_index"],
                f"{context}.event_index",
            ),
            event_time=event_time,
        )
    except ObservationWindowFormatError:
        raise
    except ValueError as error:
        raise ObservationWindowFormatError(
            f"{context} persistent event is invalid: {error}"
        ) from error


def _serialize_optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _require_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ObservationWindowFormatError(f"{context} must be a JSON object")
    return cast(Mapping[str, object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ObservationWindowFormatError(
            f"{context} keys mismatch: missing={missing!r}, extra={extra!r}"
        )


def _require_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservationWindowFormatError(f"{context} must be a non-empty string")
    if value != value.strip():
        raise ObservationWindowFormatError(f"{context} must not contain surrounding whitespace")
    return value


def _require_optional_string(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, context)


def _require_bool(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ObservationWindowFormatError(f"{context} must be boolean")
    return value


def _require_int(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObservationWindowFormatError(f"{context} must be an integer")
    return value


def _require_non_negative_int(value: object, context: str) -> int:
    result = _require_int(value, context)
    if result < 0:
        raise ObservationWindowFormatError(f"{context} must not be negative")
    return result


def _require_positive_int(value: object, context: str) -> int:
    result = _require_non_negative_int(value, context)
    if result < 1:
        raise ObservationWindowFormatError(f"{context} must be at least 1")
    return result


def _require_optional_float(value: object, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ObservationWindowFormatError(f"{context} must be numeric or null")
    result = float(value)
    if not isfinite(result):
        raise ObservationWindowFormatError(f"{context} must be finite")
    return result


def _require_datetime(value: object, context: str) -> datetime:
    text = _require_string(value, context)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ObservationWindowFormatError(f"{context} must be an ISO-8601 datetime") from error
    if parsed.utcoffset() is None:
        raise ObservationWindowFormatError(f"{context} must be timezone-aware")
    return parsed


def _require_optional_datetime(
    value: object,
    context: str,
) -> datetime | None:
    if value is None:
        return None
    return _require_datetime(value, context)


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_channel_ids(values: tuple[str, ...], field_name: str) -> None:
    for value in values:
        _validate_identifier(value, field_name)
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique values")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_non_negative_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_local_delivery_identity(
    value: tuple[str, int, int],
) -> None:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError("local_delivery_identity must be a 3-tuple")
    source_id, connection_epoch, event_index = value
    _validate_identifier(source_id, "local_delivery_identity source_id")
    _validate_non_negative_int(connection_epoch, "local_delivery_identity connection_epoch")
    if connection_epoch < 1:
        raise ValueError("local_delivery_identity connection_epoch must be at least 1")
    _validate_non_negative_int(event_index, "local_delivery_identity event_index")
