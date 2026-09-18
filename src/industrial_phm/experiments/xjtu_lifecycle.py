"""Retrospective XJTU lifecycle-third boundary shared by reference and evaluation code."""

from __future__ import annotations

LIFECYCLE_SEGMENTS = ("early_third", "middle_third", "late_third")

EARLY_THIRD, MIDDLE_THIRD, LATE_THIRD = LIFECYCLE_SEGMENTS


class XjtuLifecycleError(ValueError):
    """Raised when a lifecycle-third boundary is requested for an invalid run."""


def lifecycle_segment(position: int, run_length: int) -> str:
    """Return the retrospective third for a zero-based position in a ``1..N`` run."""
    _validate_run_length(run_length)
    if not 0 <= position < run_length:
        raise XjtuLifecycleError(f"position must fall inside 0..{run_length - 1}, got {position}")
    return LIFECYCLE_SEGMENTS[min(2, (position * 3) // run_length)]


def early_third_length(run_length: int) -> int:
    """Return how many leading acquisitions of a ``1..N`` run form its early third.

    This is ``ceil(N/3)`` and is exactly the leading block that
    :func:`lifecycle_segment` labels ``early_third``.
    """
    _validate_run_length(run_length)
    return -(-run_length // 3)


def _validate_run_length(run_length: int) -> None:
    if isinstance(run_length, bool) or not isinstance(run_length, int) or run_length <= 0:
        raise XjtuLifecycleError("run_length must be a positive integer")
