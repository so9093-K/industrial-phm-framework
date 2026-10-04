"""Named bounded-read policy for the packaged Operations application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class OperationsReadPolicy:
    """Internal product read bounds; not a user-facing runtime configuration."""

    live_max_silence: timedelta = timedelta(seconds=30)
    live_lookback_seconds: float = 60.0
    live_point_budget: int = 600
    recent_phase_result_limit: int = 500

    def __post_init__(self) -> None:
        if not isinstance(self.live_max_silence, timedelta):
            raise ValueError("live_max_silence must be a timedelta")
        if self.live_max_silence.total_seconds() <= 0:
            raise ValueError("live_max_silence must be positive")
        if (
            isinstance(self.live_lookback_seconds, bool)
            or not isinstance(self.live_lookback_seconds, Real)
            or not isfinite(self.live_lookback_seconds)
            or self.live_lookback_seconds <= 0
        ):
            raise ValueError("live_lookback_seconds must be a finite positive number")
        for value, field_name in (
            (self.live_point_budget, "live_point_budget"),
            (self.recent_phase_result_limit, "recent_phase_result_limit"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


DEFAULT_OPERATIONS_READ_POLICY = OperationsReadPolicy()
