"""Restart-safe analysis of finalized live observation windows (ADR-0008).

Each finalized window result is persisted at most once per capability, algorithm
version and analysis-policy identity. The result repository is the source of truth; a
small ledger remembers windows that cannot be analyzed (for example no channels
bound by semantic role) so they are not recomputed every cycle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms run without the lock
    fcntl = None  # type: ignore[assignment]

from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.observation_window import (
    DurableObservationWindow,
)
from industrial_phm.application.phase_unbalance import (
    PHASE_UNBALANCE_ALGORITHM_VERSION,
    PHASE_UNBALANCE_CAPABILITY_ID,
    PhaseUnbalanceConfig,
    phase_unbalance_policy_digest,
    run_phase_unbalance_on_window,
)
from industrial_phm.application.phase_unbalance_state import (
    SqlitePhaseUnbalanceRepository,
)


class WindowAnalysisState(StrEnum):
    ANALYZED = "analyzed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class WindowAnalysisOutcome:
    window_id: str
    capability_id: str
    algorithm_version: str
    analysis_policy_digest: str
    state: WindowAnalysisState
    recorded_at: datetime
    analysis_run_id: str | None = None
    reason: str | None = None

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.window_id,
            self.capability_id,
            self.algorithm_version,
            self.analysis_policy_digest,
        )


@dataclass(frozen=True, slots=True)
class WindowAnalysisCursor:
    """Progress cursor scoped to one capability/algorithm/policy identity."""

    capability_id: str
    algorithm_version: str
    analysis_policy_digest: str
    window_end: datetime
    window_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "capability_id",
            "algorithm_version",
            "analysis_policy_digest",
            "window_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if not isinstance(self.window_end, datetime) or self.window_end.utcoffset() is None:
            raise ValueError("window_end must be timezone-aware")

    @property
    def analysis_identity(self) -> tuple[str, str, str]:
        return (
            self.capability_id,
            self.algorithm_version,
            self.analysis_policy_digest,
        )


@runtime_checkable
class IncrementalObservationWindowReader(Protocol):
    def list_windows_after(
        self,
        *,
        after_window_end: datetime | None = None,
        after_window_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[DurableObservationWindow, ...]: ...


@runtime_checkable
class WindowAnalysisProgressLedger(Protocol):
    def list_skipped(self) -> tuple[WindowAnalysisOutcome, ...]: ...

    def load_cursor(
        self,
        capability_id: str,
        algorithm_version: str,
        analysis_policy_digest: str,
    ) -> WindowAnalysisCursor | None: ...

    def advance_cursor(self, cursor: WindowAnalysisCursor) -> None: ...

    def record_skip_and_advance(
        self,
        outcome: WindowAnalysisOutcome,
        cursor: WindowAnalysisCursor,
    ) -> None: ...


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """Serialize skip-ledger read-modify-write between cooperating local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a+") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def analyze_finalized_windows_incremental(
    windows: IncrementalObservationWindowReader,
    results: SqlitePhaseUnbalanceRepository,
    ledger: WindowAnalysisProgressLedger,
    *,
    config: PhaseUnbalanceConfig | None = None,
    page_size: int = 1000,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[WindowAnalysisOutcome, ...]:
    """Analyze one bounded page after a durable policy-specific cursor.

    Persistence order is deliberate: result/skip evidence is committed before the
    cursor advances. A crash may therefore recompute the last window, but cannot
    skip an unpersisted outcome.
    """
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("page_size must be a positive integer")
    if page_size > 10_000:
        raise ValueError("page_size must not exceed 10000")
    capability, algorithm = PHASE_UNBALANCE_CAPABILITY_ID, PHASE_UNBALANCE_ALGORITHM_VERSION
    requested = config or PhaseUnbalanceConfig()
    policy_digest = phase_unbalance_policy_digest(requested)
    cursor = ledger.load_cursor(capability, algorithm, policy_digest)
    pending = windows.list_windows_after(
        after_window_end=None if cursor is None else cursor.window_end,
        after_window_id=None if cursor is None else cursor.window_id,
        limit=page_size,
    )

    outcomes: list[WindowAnalysisOutcome] = []
    for window in pending:
        next_cursor = WindowAnalysisCursor(
            capability_id=capability,
            algorithm_version=algorithm,
            analysis_policy_digest=policy_digest,
            window_end=window.window_end,
            window_id=window.window_id,
        )
        try:
            analysis = run_phase_unbalance_on_window(window, config=requested, now=now)
        except ValueError as error:
            skipped = WindowAnalysisOutcome(
                window.window_id,
                capability,
                algorithm,
                policy_digest,
                WindowAnalysisState.SKIPPED,
                now(),
                reason=str(error),
            )
            ledger.record_skip_and_advance(skipped, next_cursor)
            outcomes.append(skipped)
            continue

        stored = results.record_window_result(analysis)
        reference = stored.evidence.input_reference
        if not isinstance(reference, WindowInputReference):
            raise AssertionError("window result must keep its window input reference")
        analyzed = WindowAnalysisOutcome(
            window.window_id,
            capability,
            algorithm,
            policy_digest,
            WindowAnalysisState.ANALYZED,
            stored.run.completed_at,
            analysis_run_id=stored.run.analysis_run_id,
        )
        ledger.advance_cursor(next_cursor)
        outcomes.append(analyzed)
    return tuple(outcomes)
