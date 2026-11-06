"""Display decimation preserves the full signal chart's missing-bucket boundaries."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

from industrial_phm.runtime.operations_web_explore import change_trace


def test_trace_keeps_dense_runs_connected_but_breaks_at_missing_buckets() -> None:
    start = datetime(2026, 11, 1, tzinfo=UTC)
    points = [
        (
            start + timedelta(minutes=i + (360 if i >= 600 else 0)),
            start + timedelta(minutes=i + (360 if i >= 600 else 0) + 1),
            float(i),
        )
        for i in range(1200)
    ]
    trace = change_trace(points, 60, points[600][0], points[-1][1])
    assert 2 <= len(trace) <= 54
    assert trace[0][2] is False
    assert sum(not row[2] for row in trace) == 2
    assert any(row[2] for row in trace)
    # Many raw samples are omitted for display. They must not themselves break the line.
    assert any(right[1] - left[1] > 1 and right[2] for left, right in pairwise(trace))
    for row in trace:
        position = int(row[1])
        assert datetime.fromisoformat(row[0]) == points[position][0]
        if position == 600:
            assert row[2] is False


def test_trace_preserves_sparse_samples_without_inventing_continuity() -> None:
    start = datetime(2026, 11, 1, tzinfo=UTC)
    points = [
        (start + timedelta(hours=i), start + timedelta(hours=i, seconds=60), 40.0) for i in range(4)
    ]
    assert all(row[2] is False for row in change_trace(points, 60, points[0][0], points[-1][1]))
    assert change_trace([], 60, start, start) == []
