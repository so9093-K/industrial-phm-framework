"""A replay position must not know measurements that arrived later in the record."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.genai import change_answer
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import operations_web_phm_explanation as explanations
from industrial_phm.runtime.operations_web_change_context import (
    screen_view,
    selected_change,
    view_facts,
)
from industrial_phm.runtime.operations_web_change_review import capture_change
from industrial_phm.runtime.operations_web_explore import record_findings
from industrial_phm.runtime.operations_web_forecast import acquisition_points, history_points
from industrial_phm.runtime.operations_web_load_comparison import (
    load_comparison_for_answer,
    load_comparison_query,
    read_load_comparison,
)
from industrial_phm.runtime.operations_web_vibration import acquisition_findings
from tests.integration.test_operations_web_explore import _serve
from tests.support.phm import analyze, deliver, phm_workspace

BASE = datetime(2026, 10, 1, tzinfo=UTC)


def test_later_load_and_voltage_do_not_rewrite_a_replayed_investigation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )

    def write(first: int, last: int, future: bool) -> None:
        events = []
        for index in range(first, last):
            for channel, unit, value in (
                ("current", "A", 1000.0 if future else 10.0),
                (
                    "voltage",
                    "V",
                    2000.0 if future else 220 + (10 if index >= 20 else 0) + index % 3 * 0.01,
                ),
            ):
                events.append(
                    FileBackfillEvent(
                        raw_evidence_id=f"file:meter:{'a' * 64}:{channel}-{index}",
                        source_id="meter",
                        asset_id="compressor",
                        channel_id=channel,
                        source_file="meter.csv",
                        source_sha256="a" * 64,
                        source_size_bytes=10,
                        sample_index=index,
                        event_at=BASE + timedelta(minutes=index),
                        value=value,
                        source_metadata_json='{"binding":{"definition":{"unit":"' + unit + '"}}}',
                    )
                )
        history.append_file_batch(tuple(events), batch_id=f"part-{first}")

    write(0, 40, False)
    until = BASE + timedelta(minutes=40)
    before = record_findings(workspace, "compressor", until=until)
    assert before["intervals"]
    chosen = next(row for row in before["intervals"] if row["channel"] == "voltage")
    scope = {"record_until": until.isoformat()}
    context = selected_change(workspace, "compressor", chosen["review_key"], scope)
    comparison_query = load_comparison_query(context)
    assert comparison_query is not None
    screen = screen_view(workspace, context)
    card = screen["특이사항"]
    # 한 운전 수준끼리 견준 값은 그 조건을 이름에 달고 간다(화면 제목 '약 11 A 운전일 때'처럼).
    compared = next(key for key in card if key.startswith("초기 → 특이사항 구간"))
    assert compared.endswith("운전 중인 측정끼리)") and card[compared] == "220 → 230 V"
    start = datetime.fromisoformat(chosen["start"]).astimezone(ZoneInfo("Asia/Seoul"))
    assert card["언제"].startswith(f"{start.month}월 {start.day}일 {start:%H:%M}부터")
    # '지금은 괜찮아?'에 답할 사실: 지금까지 이어지는 특이사항이 어느 신호인지와 살펴본 신호 수.
    assert screen["초기 범위를 벗어나 지금까지 이어지는 신호"] == (
        f"1개({chosen['label']}), 살펴본 신호 {before['judged']}개 중"
    )
    # 전력 값의 지금 값에는 배수를 붙이지 않는다(1배 근처를 오가는 값이다).
    assert screen["지금 값(마지막 측정)"] and not any(
        "배" in line for line in screen["지금 값(마지막 측정)"].values()
    )
    # 재생 시점 뒤의 값은 그래프에도 지금 값에도 없다.
    drawn = screen["그래프(시각, 값)"].values()
    assert all(value < 1000 for points in drawn for _, value in points)
    # 재생 중 다음 분석을 제안할 때에도 같은 운전 수준의 기간을 비교한다.
    viewed = view_facts(workspace, context, "compare")
    assert viewed[chosen["label"]].startswith("초기 220 → 특이사항 구간 230 V")
    training = history_points(workspace, "compressor", "voltage", scope)

    write(40, 90, True)
    comparison = read_load_comparison(workspace, comparison_query, chosen["interpretation_id"])
    assert comparison["status"] == "ready"
    facts = load_comparison_for_answer(comparison)
    # 대화의 차트처럼 화면의 말로: 두 중앙값과 그 차이. 견준 운전 수준은 카드처럼 값의 이름에 단다
    # (따로 두었더니 모델이 그 전류를 지금 전류와 견주었다).
    compared_load = next(key for key in facts if key.startswith("초기 → 특이사항 구간 중앙값 (약 "))
    assert compared_load.endswith(" A 운전 중인 측정끼리)")
    assert facts[compared_load].startswith("220 → 230 V (10 V 높음")
    model_started = Event()
    finish_answer = Event()

    def explain(_provider, messages, *, max_tokens):
        data = json.loads(messages[0]["content"].split("\n\n", 1)[1])
        assert data["같은 전류 범위의 실제 비교"] == facts
        model_started.set()
        assert finish_answer.wait(8)
        return "같은 전류 범위에서도 전압이 높았습니다."

    monkeypatch.setattr(change_answer, "complete_text", explain)
    monkeypatch.setattr(explanations, "_MANAGERS", {})
    job = explanations.request_phm_explanation(
        workspace.root,
        {
            "asset_id": "compressor",
            "change_id": chosen["review_key"],
            "conversation_id": "a" * 32,
            "question": "같은 부하에서도 전압이 달라졌어?",
            "analysis": "same_load",
            **scope,
        },
    )
    try:
        assert model_started.wait(8)
        store = explanations.initialize_explanation_manager(workspace.root).store
        pending = store.get(str(job["explanation_id"]))
        assert pending and pending["status"] == "pending"
        published = pending["answer"]["load_comparison"]
        assert published["status"] == "ready"
        assert published["until"] == until.isoformat()
        assert published["profile"]["series"][0]["histogram"]["a"]
        assert load_comparison_for_answer(published) == facts
    finally:
        finish_answer.set()
    after = record_findings(workspace, "compressor", until=until)
    assert after == before
    assert record_findings(workspace, "compressor")["record"]["to"] > after["record"]["to"]
    assert record_findings(workspace, "compressor", until=until) == before
    assert history_points(workspace, "compressor", "voltage", scope) == training
    assert (
        screen_view(
            workspace, selected_change(workspace, "compressor", chosen["review_key"], scope)
        )
        == screen
    )
    assert view_facts(workspace, context, "compare") == viewed
    assert max(history_points(workspace, "compressor", "voltage")[1]) > 1000
    saved = capture_change(
        workspace.root, {"asset_id": "compressor", "finding_id": chosen["review_key"], **scope}
    )
    assert saved["capture_id"]
    # Recent observation also finds a change before a user has configured a reference.
    get, stop = _serve(workspace.root)
    try:
        status, observed = get(
            "/api/v1/history/trend",
            asset_id="compressor",
            channel_id="voltage",
            source_id="meter",
            point_id="",
            range="all",
            anchor="latest",
            snapshot="latest",
            buckets=90,
            auto_reference="1",
            record_until=until.isoformat(),
        )
        assert status == 200
        assert observed["reference"]["groups"][0]["intervals"]
        assert all(b["maximum"] < 1000 for b in observed["buckets"] if b["maximum"] is not None)
        assert observed["latest_stored"] == []
    finally:
        stop()


def test_bearing_future_does_not_enter_changes_or_forecast_training(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 25):
        deliver(
            workspace, tmp_path / "waves", ordinal, 0.5 if ordinal < 13 else 2.0, amplitude_unit="g"
        )
    analyze(workspace)
    before = acquisition_findings(workspace, "bearing-a", until=24)
    training = acquisition_points(
        workspace,
        "bearing-a",
        "feature.Horizontal_vibration_signals.rms",
        count_mode=True,
        selection={"acquisition_until": "24"},
    )
    assert before["last"] == 24 and before["intervals"]
    key = before["intervals"][0]["review_key"]
    context = selected_change(workspace, "bearing-a", key, {"acquisition_until": "24"})
    screen = screen_view(workspace, context)
    assert all(points[-1][0] == 24 for points in screen["그래프(측정 번호, 값)"].values())
    for ordinal in range(25, 31):
        deliver(workspace, tmp_path / "waves", ordinal, 100.0, amplitude_unit="g")
    analyze(workspace)
    assert acquisition_findings(workspace, "bearing-a", until=24) == before
    assert screen_view(workspace, context) == screen
    assert (
        acquisition_points(
            workspace,
            "bearing-a",
            "feature.Horizontal_vibration_signals.rms",
            count_mode=True,
            selection={"acquisition_until": "24"},
        )
        == training
    )


def test_a_sampled_bearing_record_ends_its_changes_at_the_last_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long record is read sampled; a change running to the end still ends at the last one."""
    from industrial_phm.runtime import operations_web_vibration

    monkeypatch.setattr(operations_web_vibration, "_POINTS", 20)  # 39 measurements: 1, 3, …, 39
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 40):
        deliver(
            workspace, tmp_path / "waves", ordinal, 0.5 if ordinal < 25 else 2.0, amplitude_unit="g"
        )
    analyze(workspace)
    found = acquisition_findings(workspace, "bearing-a")
    assert found["last"] == 39 and found["intervals"]
    assert max(row["to"] for row in found["intervals"]) == 39
    # Sampled every 2nd measurement, the trace is still one line, not 20 separate dots.
    assert all(all(row["trace_join"][1:]) for row in found["intervals"])


def test_only_a_clear_change_in_vibration_level_is_raised(tmp_path: Path) -> None:
    """A level 1.2 times the start is ordinary drift; 1.6 times is a change, told by its RMS."""
    found = {}
    for rise in (1.2, 1.6):
        workspace = phm_workspace(tmp_path / str(rise))
        for ordinal in range(1, 31):
            deliver(
                workspace,
                tmp_path / f"waves-{rise}",
                ordinal,
                0.5 if ordinal < 16 else 0.5 * rise,
                amplitude_unit="g",
            )
        analyze(workspace)
        found[rise] = acquisition_findings(workspace, "bearing-a")
    assert found[1.2]["judged"] and found[1.2]["intervals"] == []
    changes = found[1.6]["intervals"]
    assert changes and all(row["feature"].endswith(".rms") for row in changes)
    # The peak rose with it; the signal's mean and skewness never stand for the bearing's state.
    related = [row["feature"].rsplit(".", 1)[-1] for row in changes[0]["related"]]
    assert "absolute_peak" in related
    assert not {"mean", "skewness"} & set(related)


def test_a_change_that_speeds_up_rises_more_in_its_second_half(tmp_path: Path) -> None:
    """The halves are read from the measurements themselves, so a quickening rise shows as one."""
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 41):
        step = max(0, ordinal - 20)
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + 0.01 * step**2, amplitude_unit="g")
    analyze(workspace)
    change = acquisition_findings(workspace, "bearing-a")["intervals"][0]
    first, second = change["halves"]
    assert first["from"] == change["from"] and second["to"] == change["to"] == 40
    assert first["to"] == second["from"]
    assert 0 < first["change"] < second["change"]
