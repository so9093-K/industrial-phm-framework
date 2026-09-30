"""Explicit re-reads of persisted analysis results written by another process.

Operations does not run or supervise analysis runners; it only re-reads the
repository they write to when a person asks. A failed read keeps the previously
loaded results and reports the failure separately, so stale results are never
mistaken for a successful refresh.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class _Run(Protocol):
    @property
    def analysis_run_id(self) -> str: ...


class _Result(Protocol):
    @property
    def run(self) -> _Run: ...


@dataclass(frozen=True, slots=True)
class AnalysisResultsLoad[T: _Result]:
    """Results from the last successful read and the outcome of the latest attempt.

    ``error`` names the latest failed read; ``results`` and ``loaded_at`` then still
    describe the earlier successful read. ``added`` counts runs that were new in the
    latest successful read.
    """

    results: tuple[T, ...]
    loaded_at: datetime | None
    error: str = ""
    added: int = 0


def load_analysis_results[T: _Result](
    load: Callable[[], tuple[T, ...]], *, now: datetime
) -> AnalysisResultsLoad[T]:
    """First read at startup; nothing earlier to keep when it fails."""
    return reload_analysis_results(load, AnalysisResultsLoad((), None), now=now)


def reload_analysis_results[T: _Result](
    load: Callable[[], tuple[T, ...]],
    previous: AnalysisResultsLoad[T],
    *,
    now: datetime,
) -> AnalysisResultsLoad[T]:
    try:
        results = load()
    except (OSError, ValueError) as error:
        return AnalysisResultsLoad(
            previous.results, previous.loaded_at, f"{type(error).__name__}: {error}"
        )
    known = {result.run.analysis_run_id for result in previous.results}
    added = sum(result.run.analysis_run_id not in known for result in results)
    return AnalysisResultsLoad(tuple(results), now, "", added)


def retained_option(options: Mapping[str, str], selected_value: str | None) -> str | None:
    """Label whose value is still the selection, else the first (newest) label."""
    if not options:
        return None
    return next(
        (label for label, value in options.items() if value == selected_value),
        next(iter(options)),
    )
