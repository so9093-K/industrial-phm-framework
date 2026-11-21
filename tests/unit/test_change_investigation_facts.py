"""What an AI answer about a power change rests on: the period, level and order on screen."""

from __future__ import annotations

from typing import Any

from industrial_phm.runtime.operations_web_change_context import history_investigation


def _change(
    key: str, channel: str, start: str, end: str, before: float, after: float
) -> dict[str, Any]:
    return {
        "review_key": key * 64,
        "key": "signal-" + channel,
        "label": channel,
        "channel": channel,
        "unit": "V",
        "start": start,
        "end": end,
        "reference_value": before,
        "typical_value": after,
    }


def test_a_power_change_carries_its_level_mix_and_the_changes_drawn_beside_it() -> None:
    r = _change("a", "R상전압", "2020-10-04T00:19:00+00:00", "2020-10-04T22:31:00+00:00", 222, 226)
    s = _change("b", "S상전압", "2020-10-04T00:19:00+00:00", "2020-10-04T08:19:00+00:00", 222, 225)
    t = _change("c", "T상전압", "2020-10-04T18:05:00+00:00", "2020-10-04T21:38:00+00:00", 221, 224)
    current = {
        "reference": 10.7,
        "current": 12.7,
        "state": "within",
        "label": "R상전류",
        "unit": "A",
        "key": "signal-R상전류",
    }
    context = {
        "history_change": {
            **r,
            "band": 1,
            "operation": {
                "key": "load",
                "baseline": [0, 0.15, 0.44, 0.41],
                "interval": [0, 0.44, 0.56, 0],
            },
            "related": [
                {
                    "reference": 222,
                    "current": 225,
                    "state": "higher",
                    "label": "S상전압",
                    "unit": "V",
                    "key": "signal-S상전압",
                },
                current,
            ],
        },
        "operation": [
            {
                "key": "load",
                "unit": "A",
                "levels": [{"typical": 10.6}, {"typical": 31.4}, {"typical": 61.9}],
            }
        ],
        "channels": ["R상전압", "S상전압", "T상전압"],
        "episode": [r, s, t],
    }
    out = history_investigation(context)
    facts, targets = out["facts"], out["targets"]

    # Korean time, as the chart reads: 00:19 UTC is 09:19, and 22:31 UTC is the next morning.
    assert "2020년 10월 4일 09:19부터 10월 5일 07:31까지" in facts["subject"]
    # Values compared at one operating level say so; English states do not reach the model.
    assert facts["related_1"].startswith("약 11 A 운전 중인 측정끼리, ")
    assert "within" not in facts["related_1"] and "비교 범위 안" in facts["related_1"]
    # Whether the load changed is the level mix of the two periods.
    assert facts["operating_share"] == (
        "운전 수준별 측정 비중(비교 구간 → 변화 구간): 약 11 A 운전 15% → 44%, "
        "약 31 A 운전 44% → 56%, 약 62 A 운전 41% → 0%."
    )
    assert facts["order"].startswith(
        "같은 시기 변화의 시작 순서: R상전압·S상전압(10월 4일 09:19) → T상전압(10월 5일 03:05)."
    )
    # A related phase that is itself a drawn change points at that change; current does not.
    assert targets["related_0"]["review_key"] == s["review_key"]
    assert targets["related_0"]["where"] == "10월 4일 09:19~17:19"
    assert targets["related_1"] == {
        "kind": "signal",
        "label": "R상전류",
        "before": 10.7,
        "after": 12.7,
        "unit": "A",
    }
    assert targets["episode_1"]["review_key"] == t["review_key"]
    assert targets["operating_share"]["levels"] == [
        "정지",
        "약 11 A 운전",
        "약 31 A 운전",
        "약 62 A 운전",
    ]
    assert targets["operating_share"]["b"] == [0, 0.44, 0.56, 0]
    # What the investigation looked at, one '항목 · 결과' row each, the selected change first.
    assert [(row["label"], row["result"]) for row in out["steps"]] == [
        ("R상전압", "222 → 226 V"),
        ("약 11 A 운전 비중", "15% → 44%"),
        ("같은 운전 수준끼리 비교", "약 11 A 운전"),
        ("S상전압", "222 → 225 V"),
        ("R상전류", "10.7 → 12.7 A"),
        ("같은 시기 변화", "S상전압·T상전압"),
    ]
    assert all(row["fact"] in facts for row in out["steps"])


def test_when_the_load_changed_is_read_from_the_same_strip_as_the_screen() -> None:
    """Each hour's dominant level, merged into runs; a one-column flicker does not split a run."""
    hours = [f"2020-10-03T{hour:02d}:00:00+00:00" for hour in range(24)]
    levels = [3] * 10 + [2] * 3 + [3] + [2] * 10  # 13시에 한 칸만 다시 높은 부하
    change = {
        "review_key": "a" * 64,
        "label": "R상전압",
        "unit": "V",
        "start": "2020-10-03T16:00:00+00:00",
        "end": "2020-10-03T20:00:00+00:00",
        "reference_value": 222,
        "typical_value": 226,
        "band": 1,
        "operation": {"key": "load", "baseline": [0, 0, 0.5, 0.5], "interval": [0, 0, 1, 0]},
        "related": [],
    }
    context = {
        "history_change": change,
        "operation": [
            {
                "key": "load",
                "unit": "A",
                "bucket_seconds": 3600,
                "levels": [{"typical": 10.6}, {"typical": 31.4}, {"typical": 61.9}],
                "timeline": [
                    [at, [0, 0, 5 if level == 2 else 0, 5 if level == 3 else 0]]
                    for at, level in zip(hours, levels, strict=True)
                ],
            }
        ],
        "channels": ["R상전압"],
        "episode": [change],
    }
    out = history_investigation(context)
    facts = out["facts"]
    # Window 08:00-23:00 UTC (the change and twice its length before it), shown in Korean time.
    assert facts["operating_flow"].endswith(
        "10월 3일 17:00~10월 3일 19:00 약 62 A 운전, 10월 3일 19:00~10월 4일 09:00 약 31 A 운전."
    )
    # Hour by hour the dominant level is not a checked row: it hides levels mixed within an hour.
    assert "operating_flow" not in [row["fact"] for row in out["steps"]]
