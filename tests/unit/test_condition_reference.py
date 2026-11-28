"""The 3-phase comparison judges the target against an earlier period of the same load."""

from datetime import UTC, datetime, timedelta

from industrial_phm.application.measurement_history import ValueOccupancy, ValueOccupancyBucket
from industrial_phm.application.operating_state import OperatingLevels
from industrial_phm.runtime.operations_web_condition import same_level_reference
from industrial_phm.runtime.operations_web_operation import StreamOperation

DAY0 = datetime(2020, 10, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _operation(hours: list[tuple[int, int]]) -> StreamOperation:
    """One bucket per hour holding 60 observations at 11 A (band 1) or 31 A (band 2)."""
    buckets = tuple(
        ValueOccupancyBucket(
            DAY0 + index * HOUR,
            DAY0 + (index + 1) * HOUR,
            (0, 60 if band == 1 else 0, 60 if band == 2 else 0),
        )
        for index, (band, _) in enumerate(hours)
    )
    occupancy = ValueOccupancy(
        DAY0, DAY0 + len(hours) * HOUR, 3600.0, (1.0, 20.0), 1.0, 40.0, buckets
    )
    levels = OperatingLevels((1.0, 20.0), (11.0, 31.0))
    return StreamOperation("current", levels, occupancy, tuple(b.bucket_start for b in buckets))


def test_a_target_at_a_load_the_day_before_lacked_is_judged_against_a_day_that_had_it() -> None:
    # 첫날은 11 A, 둘째 날은 31 A만, 셋째 날(분석 기간)은 11 A로 돌았다.
    operation = _operation([(1, 0)] * 24 + [(2, 0)] * 24 + [(1, 0)] * 24)
    start, end = DAY0 + 48 * HOUR, DAY0 + 72 * HOUR
    moved = same_level_reference(operation, start, end, start - 24 * HOUR, start)
    assert moved == (DAY0, DAY0 + 24 * HOUR)


def test_the_day_before_stays_when_it_already_judges_the_target() -> None:
    operation = _operation([(1, 0)] * 24 + [(1, 0)] * 24 + [(1, 0)] * 24)
    start, end = DAY0 + 48 * HOUR, DAY0 + 72 * HOUR
    assert same_level_reference(operation, start, end, start - 24 * HOUR, start) is None
    # 앞선 어느 날에도 그 운전 상태가 없으면 바로 앞 날을 그대로 둔다.
    other = _operation([(2, 0)] * 48 + [(1, 0)] * 24)
    assert same_level_reference(other, start, end, start - 24 * HOUR, start) is None
