from __future__ import annotations

from typing import Any

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import explanation_context
from industrial_phm.application.phm_range import (
    level_shift,
    range_analysis,
    rank_correlation,
    series_shape,
)
from industrial_phm.genai.phm_answer import answer_input, text_issues, verified_summary
from industrial_phm.models.package import StepKind
from tests.support.phm import analyze, deliver, phm_workspace

SCALES = (0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2)


def test_rank_correlation_reads_order_not_magnitude() -> None:
    assert rank_correlation([1, 2, 3, 10, 50]) == pytest.approx(1.0)
    assert rank_correlation([5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert abs(rank_correlation([1, 3, 1, 3, 1, 3])) < 0.5


def test_level_shift_finds_where_two_levels_meet() -> None:
    at, explained = level_shift([1.0, 1.1, 0.9, 1.0, 5.0, 5.2, 4.9, 5.1])  # type: ignore[misc]
    assert at == 4 and explained > 0.95
    assert level_shift([2.0, 2.0, 2.0, 2.0]) is None


def test_shape_needs_enough_results_and_names_positions() -> None:
    assert series_shape([1, 2, 3], [1.0, 2.0, 3.0]) == {"count": 3, "trend": "insufficient"}
    shape = series_shape([10, 11, 12, 13, 14, 15], [1.0, 1.0, 1.2, 4.0, 4.1, 4.0])
    assert shape["trend"] == "increasing"
    assert shape["largest_step"] == {
        "from": 12,
        "to": 13,
        "direction": "increase",
        "share_of_span": pytest.approx(0.903, abs=1e-3),
    }
    assert shape["level_shift"]["at"] == 13 and shape["level_shift"]["direction"] == "increase"
    noisy = series_shape(list(range(8)), [1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0, 3.0])
    assert noisy["trend"] == "mixed" and noisy["level_shift"] is None


def test_values_that_do_not_move_have_no_direction_or_moment() -> None:
    assert series_shape(list(range(6)), [2.0] * 6) == {
        "count": 6,
        "trend": "flat",
        "largest_step": None,
        "level_shift": None,
    }


def test_a_gradual_rise_is_not_called_a_level_shift() -> None:
    line = series_shape(list(range(1, 9)), [1.0, 2, 3, 4, 5, 6, 7, 8])
    assert line["trend"] == "increasing" and line["steady"] is True
    assert line["level_shift"] is None and line["largest_step"] is None
    step = series_shape(list(range(1, 9)), [1.0, 1.1, 0.9, 1.0, 5.0, 5.2, 4.9, 5.1])
    assert step["level_shift"]["at"] == 5 and step["steady"] is False


def test_an_overall_rise_with_a_large_drop_is_not_steady() -> None:
    dip = series_shape(list(range(1, 9)), [1.0, 2, 3, 4, 1.5, 6, 7, 8])
    assert dip["trend"] == "increasing" and dip["steady"] is False


@pytest.fixture(scope="module")
def stored(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("range")
    workspace = phm_workspace(root / "ws")
    for ordinal, scale in enumerate(SCALES, start=1):
        deliver(workspace, root / "waves", ordinal, scale)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    return {
        "workspace": workspace,
        "store": store,
        "context": explanation_context(
            store, workspace.models_path, snapshots, "anomaly-a", 8, compare_position=1
        ),
    }


def test_range_reads_every_analyzed_result_between_the_selection(stored: dict[str, Any]) -> None:
    rms = "feature.Horizontal_vibration_signals.rms"
    span = range_analysis(stored["store"], "anomaly-a", StepKind.ACQUISITION_SNAPSHOT, 2, 8, [rms])
    assert span["steps"] == 7 and span["first"] == 2 and span["last"] == 8
    assert span["primary"]["level_shift"]["at"] == 5
    assert span["features"][rms]["level_shift"]["at"] == 5
    assert span["labels"] == {"2": "#2", "4": "#4", "5": "#5", "8": "#8"}


def test_a_long_range_is_sampled_over_its_whole_length(stored: dict[str, Any]) -> None:
    results, total = stored["store"].analyzed_between("anomaly-a", 1, 8, max_points=3)
    assert total == 8 and [r.position for r in results] == [1, 4, 7, 8]
    span = range_analysis(stored["store"], "anomaly-a", StepKind.ACQUISITION_SNAPSHOT, 1, 8, [])
    assert (span["steps"], span["points"], span["sampled"]) == (8, 8, False)
    assert (span["analyzed_first"], span["analyzed_last"]) == (1, 8)


def test_since_when_is_answered_with_the_level_shift_label(stored: dict[str, Any]) -> None:
    context = {**stored["context"], "question": "언제부터 신호가 달라졌어?"}
    payload = answer_input(context)
    assert payload["positions"] == {"compared": "#1", "selected": "#8"}
    assert payload["range"]["level_shifts"][0] == {
        "name": "이상 점수",
        "at": "#5",
        "change": "높아짐",
    }
    vague = "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다."
    assert "#5" in text_issues(vague, payload, field="summary")[-1]
    cited = "이상 점수가 증가했고 #5에서 수준이 높아졌습니다."
    assert text_issues(cited, payload, field="summary") == []
    payload["range"]["level_shifts"].append({"name": "x", "at": "#10", "change": "높아짐"})
    both = "이상 점수가 증가했고 #1 이후 #10에서 수준이 높아졌습니다."
    assert text_issues(both, payload, field="summary") == []
    summary, _, _ = verified_summary(payload)
    assert "#5에서 높아졌습니다." in summary


def test_period_words_follow_the_range(stored: dict[str, Any]) -> None:
    payload = answer_input(stored["context"])
    payload["range"]["primary"]["trend"] = "꾸준히 증가"
    assert text_issues("이상 점수가 꾸준히 증가했습니다.", payload, field="summary") == []
    payload["range"]["primary"]["trend"] = "대체로 증가"
    assert text_issues("이상 점수가 증가하는 추세입니다.", payload, field="summary") == []
    steady = text_issues("이상 점수가 꾸준히 증가했습니다.", payload, field="summary")
    assert steady and "대체로 증가" in steady[0]
    payload["range"]["primary"]["trend"] = "오르내림"
    issue = text_issues("이상 점수가 증가하는 추세입니다.", payload, field="summary")
    assert issue and "오르내림" in issue[0]


def test_spike_omitted_from_the_flow_sample_is_still_the_exact_largest_change(
    stored: dict[str, Any],
    tmp_path,
) -> None:
    import json
    import sqlite3

    rms = "feature.Horizontal_vibration_signals.rms"
    path = tmp_path / "long-range.sqlite"
    with sqlite3.connect(stored["store"].path) as original, sqlite3.connect(path) as database:
        original.backup(database)
        template = list(
            database.execute(
                "SELECT * FROM step_result WHERE binding_id='anomaly-a' LIMIT 1"
            ).fetchone()
        )
        database.execute("DELETE FROM step_result WHERE binding_id='anomaly-a'")
        rows = []
        for position in range(1, 5001):
            row = template.copy()
            row[1], row[2], row[4], row[9] = (
                f"snapshot:{position}",
                position,
                f"run-{position}",
                position,
            )
            value = 9.0 if position == 2500 else 1.0
            row[8] = json.dumps({"task": "anomaly-score", "score": value})
            row[13] = json.dumps({rms: value})
            rows.append(tuple(row))
        database.executemany(
            "INSERT INTO step_result VALUES (" + ",".join("?" for _ in template) + ")", rows
        )
    store = SqlitePhmAnalysisStore(path)
    sampled, total = store.analyzed_between("anomaly-a", 1, 5000)
    assert total == 5000 and all(item.position != 2500 for item in sampled)
    span = range_analysis(store, "anomaly-a", StepKind.ACQUISITION_SNAPSHOT, 1, 5000, [rms])
    for shape in (span["primary"], span["features"][rms]):
        assert shape["largest_step"]["from"] == 2499
        assert shape["largest_step"]["to"] == 2500
        assert shape["largest_step"]["share_of_span"] == 1.0
        assert shape["trend"] != "flat"
    assert span["labels"]["2500"] == "#2500"
    assert span["largest_step_basis"] == "adjacent-analyzed-results-in-full-range"
    # The requested boundary must not bring in the spike just outside the interval.
    outside = range_analysis(store, "anomaly-a", StepKind.ACQUISITION_SNAPSHOT, 2501, 5000, [rms])
    assert outside["primary"]["trend"] == "flat"
    assert outside["primary"]["largest_step"] is None

    # Missing measurements cannot be bridged into a spurious single change.
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE step_result SET features=json_set(features, '$.sparse', 1) "
            "WHERE binding_id='anomaly-a' AND position=2501"
        )
        database.execute(
            "UPDATE step_result SET features=json_set(features, '$.sparse', 9) "
            "WHERE binding_id='anomaly-a' AND position=2503"
        )
    missing = store.analyzed_change_stats(
        "anomaly-a", 2501, 2504, output_key="score", features=["sparse"]
    )
    assert missing["sparse"]["pairs"] == 0 and missing["sparse"]["delta"] is None
