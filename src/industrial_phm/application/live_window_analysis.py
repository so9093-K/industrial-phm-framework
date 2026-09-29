"""Restart-safe analysis of finalized live observation windows (ADR-0008).

Each finalized window result is persisted at most once per capability, algorithm
version and analysis-policy identity. The result repository is the source of truth; a
small ledger remembers windows that cannot be analyzed (for example no channels
bound by semantic role) so they are not recomputed every cycle.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms run without the lock
    fcntl = None  # type: ignore[assignment]

from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.observation_window import (
    DurableObservationWindow,
    ObservationWindowRepository,
)
from industrial_phm.application.phase_unbalance import (
    PHASE_UNBALANCE_ALGORITHM_VERSION,
    PHASE_UNBALANCE_CAPABILITY_ID,
    PhaseUnbalanceConfig,
    phase_unbalance_policy_digest,
    run_phase_unbalance_on_window,
)
from industrial_phm.application.phase_unbalance_state import (
    JsonPhaseUnbalanceRepository,
    window_result_key,
)

_LEDGER_SCHEMA = "industrial-phm-window-analysis-ledger-v1"


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


class JsonWindowAnalysisLedger:
    """Durable record of windows skipped as not analyzable (atomic replace)."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    def list_skipped(self) -> tuple[WindowAnalysisOutcome, ...]:
        if not self._path.exists():
            return ()
        root = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(root, dict) or root.get("schema") != _LEDGER_SCHEMA:
            raise ValueError(f"unsupported window analysis ledger schema in {self._path}")
        return tuple(
            WindowAnalysisOutcome(
                window_id=item["window_id"],
                capability_id=item["capability_id"],
                algorithm_version=item["algorithm_version"],
                analysis_policy_digest=item["analysis_policy_digest"],
                state=WindowAnalysisState.SKIPPED,
                recorded_at=datetime.fromisoformat(item["recorded_at"]),
                reason=item["reason"],
            )
            for item in root["skipped"]
        )

    def record_skip(self, outcome: WindowAnalysisOutcome) -> None:
        if outcome.state != WindowAnalysisState.SKIPPED:
            raise ValueError("ledger records skipped windows only")
        with _exclusive(self._path):
            skipped = {item.key: item for item in self.list_skipped()}
            if outcome.key in skipped:
                return
            skipped[outcome.key] = outcome
            payload = {
                "schema": _LEDGER_SCHEMA,
                "skipped": [
                    {
                        "window_id": item.window_id,
                        "capability_id": item.capability_id,
                        "algorithm_version": item.algorithm_version,
                        "analysis_policy_digest": item.analysis_policy_digest,
                        "recorded_at": item.recorded_at.isoformat(),
                        "reason": item.reason,
                    }
                    for item in sorted(skipped.values(), key=lambda o: o.key)
                ],
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(handle.name, self._path)
            finally:
                Path(handle.name).unlink(missing_ok=True)


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


def analyze_finalized_windows(
    windows: ObservationWindowRepository,
    results: JsonPhaseUnbalanceRepository,
    ledger: JsonWindowAnalysisLedger,
    *,
    config: PhaseUnbalanceConfig | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[WindowAnalysisOutcome, ...]:
    """Analyze every finalized window not yet analyzed or skipped; return new outcomes.

    Safe to repeat and restart: the same window/capability/algorithm/policy
    result is persisted once. Concurrent runners may compute the same pending
    window, but repository locking prevents duplicate result persistence.
    """
    capability, algorithm = PHASE_UNBALANCE_CAPABILITY_ID, PHASE_UNBALANCE_ALGORITHM_VERSION
    requested = config or PhaseUnbalanceConfig()
    policy_digest = phase_unbalance_policy_digest(requested)
    done = {key for result in results.list_results() if (key := window_result_key(result))}
    done |= {outcome.key for outcome in ledger.list_skipped()}
    pending: Sequence[DurableObservationWindow] = sorted(
        (
            w
            for w in windows.list_windows()
            if (w.window_id, capability, algorithm, policy_digest) not in done
        ),
        key=lambda w: (w.window_end, w.window_id),
    )
    outcomes = []
    for window in pending:
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
            ledger.record_skip(skipped)
            outcomes.append(skipped)
            continue
        stored = results.record_window_result(analysis)
        reference = stored.evidence.input_reference
        if not isinstance(reference, WindowInputReference):
            raise AssertionError("window result must keep its window input reference")
        outcomes.append(
            WindowAnalysisOutcome(
                window.window_id,
                capability,
                algorithm,
                policy_digest,
                WindowAnalysisState.ANALYZED,
                stored.run.completed_at,
                analysis_run_id=stored.run.analysis_run_id,
            )
        )
    return tuple(outcomes)
