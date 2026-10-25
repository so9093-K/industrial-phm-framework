"""Pure rules of stored-history window steps (ADR-0032)."""

from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.history_window import (
    HistoryModelRequest,
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
