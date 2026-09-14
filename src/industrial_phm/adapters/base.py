"""Protocol implemented by dataset- or equipment-specific adapters."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

from industrial_phm.contracts import CanonicalTimeSeries


@runtime_checkable
class DomainAdapter(Protocol):
    """Translate domain-specific source data into the canonical PHM contract."""

    @property
    def domain(self) -> str:
        """Stable domain identifier used for configuration and provenance."""
        ...

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        """Yield canonical time-series records from ``source``."""
        ...
