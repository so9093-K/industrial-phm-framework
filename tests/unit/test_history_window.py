"""Pure rules of stored-history window steps (ADR-0032)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.history_window import (
    HistoryModelRequest,
    build_history_model,
    feature_names,
    feature_set_id,
    group_windows,
    window_features,
    window_seconds_of,
)
from industrial_phm.application.phm_signal_comparison import feature_label

AT = datetime(2026, 10, 15, 0, 3, tzinfo=UTC)


def _obs(
    channel: str, minute: int, value: float | None, *, good: bool = True
) -> ChannelObservation:
    return ChannelObservation(
        source_id="s",
        measurement_point_id=None,
        channel_id=channel,
        event_at=AT + timedelta(minutes=minute),
        value=value,
        conflicting=False,
        source_quality_good=good,
        observed_property=None,
        scope=None,
        unit=None,
        semantic_version=None,
    )


def test_feature_set_names_its_window_length_and_rejects_others() -> None:
    assert feature_set_id(600) == "history-window-stats-v1:600s"
    assert window_seconds_of("history-window-stats-v1:600s") == 600
    assert window_seconds_of("history-window-stats-v1:601s") is None
    assert window_seconds_of("electrical-window-v1") is None
    assert feature_names(["a"]) == ("a.mean", "a.std", "a.min", "a.max")
    with pytest.raises(ValueError):
        feature_set_id(42)


def test_windows_are_epoch_aligned_and_a_thin_channel_is_a_skip_reason() -> None:
    rows = [_obs("a", m, float(m)) for m in range(20)] + [_obs("b", 0, 1.0), _obs("b", 1, None)]
    windows = group_windows(rows, seconds=600, measurement_point_id=None)
    assert [w.start.minute for w in windows] == [0, 10, 20]
    values, reason = window_features(windows[1], ["a"])
    assert values == {
        "a.mean": 11.5,
        "a.std": pytest.approx(2.8722813),
        "a.min": 7.0,
        "a.max": 16.0,
    }
    assert reason is None
    values, reason = window_features(windows[0], ["a", "b"])
    assert values is None and reason == "b: 1 usable values, at least 3 needed"


def test_request_and_labels_say_what_a_person_chose() -> None:
    with pytest.raises(ValueError, match="distinct"):
        HistoryModelRequest("a", "s", ("x", "x"), AT, AT + timedelta(days=1), 600)
    with pytest.raises(ValueError, match="end after"):
        HistoryModelRequest("a", "s", ("x",), AT, AT, 600)
    assert feature_label("motor_temp_c.std") == "motor_temp_c 표준편차"
    assert feature_label("feature.Horizontal_vibration_signals.rms") == "수평 진동 RMS"


def _unit(channel: str, minute: int, value: float, unit: str) -> ChannelObservation:
    return replace(_obs(channel, minute, value), unit=unit)


def test_values_of_different_units_are_never_one_feature() -> None:
    mixed = group_windows(
        [_unit("a", m, 1.0 + m, "mm/s") for m in range(3)] + [_unit("a", 4, 0.1, "g")],
        seconds=600,
        measurement_point_id=None,
    )[0]
    assert window_features(mixed, ["a"]) == (
        None,
        "a: values with different units or meanings in one window",
    )
    other = group_windows(
        [_unit("a", m, 1.0 + m, "g") for m in range(3)], seconds=600, measurement_point_id=None
    )[0]
    values, reason = window_features(other, ["a"], {"a": [None, None, "mm/s", None]})
    assert values is None and reason is not None
    assert "differs from the reference period (-/-/mm/s -> -/-/g)" in reason


class _History:
    def __init__(self, rows: list[ChannelObservation]) -> None:
        self.rows = rows

    def current_snapshot_id(self) -> int:
        return 1

    def history_stream_extent(self, *args: object, **kwargs: object) -> None:
        return None

    def query_channel_observations(
        self, asset_id: str, *, start_at: datetime, end_at: datetime, **_: object
    ) -> tuple[ChannelObservation, ...]:
        return tuple(r for r in self.rows if start_at <= r.event_at < end_at)


def test_a_reference_period_whose_unit_changes_builds_no_model(tmp_path: Path) -> None:
    rows = [_unit("a", m, 1.0 + (m % 7), "mm/s" if m < 300 else "g") for m in range(600)]
    request = HistoryModelRequest(
        "asset", "s", ("a",), AT - timedelta(minutes=3), AT + timedelta(hours=10), 600
    )
    built = build_history_model(
        tmp_path, _History(rows), request, created_at=AT, code_revision="test"
    )
    assert built.package_id is None and "단위나 의미가 바뀝니다" in str(built.reason)
    assert not list(tmp_path.glob("*/package.json"))


def _loaded(minutes: range, current: float, voltage: float) -> list[ChannelObservation]:
    """A minute series at one load: the current and a voltage that sags a little with it."""
    rows = []
    for m in minutes:
        jitter = (m * 37 % 11) / 10
        rows += [_obs("i", m, current + jitter), _obs("v", m, voltage + jitter / 5)]
    return rows


def test_each_operating_level_is_learned_and_judged_apart(tmp_path: Path) -> None:
    """A window is compared only with windows of its own load; a load the reference period
    hardly ran at is not judged, rather than being called anomalous for its other voltage."""
    from industrial_phm.application.history_window import LEVEL_RECIPE_ID, LevelBasis
    from industrial_phm.models.package import (
        OutsideLearnedLevel,
        fit_row_ranges,
        load_model_package,
    )

    # 48 ten-minute windows at about 62 A, then 30 at about 31 A, then 6 at about 11 A.
    rows = (
        _loaded(range(0, 480), 62.0, 214.0)
        + _loaded(range(480, 780), 31.0, 220.0)
        + _loaded(range(780, 840), 11.0, 226.0)
    )
    levels = LevelBasis("i", (1.0, 20.0, 45.0), (11.0, 31.0, 62.0))
    request = HistoryModelRequest(
        "asset", "s", ("v",), AT - timedelta(minutes=3), AT + timedelta(minutes=840), 600
    )
    built = build_history_model(
        tmp_path, _History(rows), request, created_at=AT, code_revision="test", levels=levels
    )
    assert built.package_id is not None and built.package_id.startswith(LEVEL_RECIPE_ID)
    assert built.levels is not None and built.levels["learned"] == ["2", "3"]
    assert built.levels["reference_windows"]["1"] < 24
    package = load_model_package(tmp_path / built.package_id)
    # The current is read with the chosen signal to place each window at its level.
    assert list(package.manifest.input.channels) == ["v", "i"]
    names = package.manifest.input.feature_names

    def row(current: float, voltage: float) -> list[float]:
        # A later window computed the way every step is: from its own observations.
        (window,) = group_windows(
            _loaded(range(897, 907), current, voltage), seconds=600, measurement_point_id=None
        )
        values, _ = window_features(window, ["v", "i"])
        assert values is not None
        return [values[name] for name in names]

    # Each window is read against its own level: 220 V is usual at about 31 A and stays under
    # that level's threshold, while 226 V at 62 A scores above what 62 A usually scores.
    usual_62, odd_62, usual_31 = package.evaluate(
        [row(62.0, 214.0), row(62.0, 226.0), row(31.0, 220.0)]
    )
    assert usual_62 <= 1 and usual_31 <= 1 and odd_62 > usual_62
    with pytest.raises(OutsideLearnedLevel, match="operating level not learned: 11 A"):
        package.evaluate([row(11.0, 226.0)])
    # What raised the odd window's score is its voltage, read against its own level's forest.
    parts = package.feature_contributions([row(62.0, 226.0)])
    assert parts is not None
    voltage = sum(v for name, v in parts[0].items() if name.startswith("v."))
    current = sum(v for name, v in parts[0].items() if name.startswith("i."))
    assert voltage > 0 and voltage > current
    with pytest.raises(OutsideLearnedLevel):
        package.feature_contributions([row(11.0, 226.0)])
    # The learned range of a feature is the one of the level the window ran at.
    at_62 = fit_row_ranges(tmp_path / built.package_id, features={"i.mean": 62.0})
    at_31 = fit_row_ranges(tmp_path / built.package_id, features={"i.mean": 31.0})
    assert at_62["v.mean"][1] < 216 < 218 < at_31["v.mean"][0]
    assert fit_row_ranges(tmp_path / built.package_id, features={"i.mean": 11.0}) == {}
    # Pressing again with the same choices reuses the model.
    again = build_history_model(
        tmp_path, _History(rows), request, created_at=AT, code_revision="test", levels=levels
    )
    assert again.reused and again.package_id == built.package_id


def test_no_level_with_enough_reference_windows_builds_nothing(tmp_path: Path) -> None:
    from industrial_phm.application.history_window import LevelBasis

    rows = _loaded(range(0, 200), 62.0, 214.0) + _loaded(range(200, 400), 31.0, 220.0)
    request = HistoryModelRequest(
        "asset", "s", ("v",), AT - timedelta(minutes=3), AT + timedelta(minutes=400), 600
    )
    built = build_history_model(
        tmp_path,
        _History(rows),
        request,
        created_at=AT,
        code_revision="test",
        levels=LevelBasis("i", (1.0, 20.0, 45.0), (11.0, 31.0, 62.0)),
    )
    assert built.package_id is None
    assert "약 62 A 운전 20개" in str(built.reason) and "약 31 A 운전 20개" in str(built.reason)


def test_a_signal_without_values_in_the_reference_is_named_not_the_period(tmp_path: Path) -> None:
    # 가져올 때 비운 칸(다른 item을 옮긴 값)만 있는 신호: 기간을 늘려도 모델을 만들 수 없다.
    rows = _loaded(range(0, 400), 62.0, 214.0) + [_obs("h", m, None) for m in range(0, 400)]
    request = HistoryModelRequest(
        "asset", "s", ("v", "h"), AT - timedelta(minutes=3), AT + timedelta(minutes=400), 600
    )
    built = build_history_model(
        tmp_path, _History(rows), request, created_at=AT, code_revision="test"
    )
    assert built.package_id is None
    assert (
        built.reason
        == "h 신호는 기준 기간에 값이 없습니다. 이 신호를 빼거나 값이 있는 기간을 고르세요."
    )
