import pytest

pytest.importorskip("anywidget")
from industrial_phm.apps.monitor_widget import MonitorWidget


def test_widget_acknowledges_rejected_and_failed_actions():
    rejected = MonitorWidget({}, lambda event: False)
    rejected.event = {"kind": "focus", "channel": "missing", "sequence": 1}
    assert rejected.response["status"] == "rejected"
    assert rejected.response["sequence"] == 1
    assert "Refresh" in rejected.response["message"]
    rejected.close()

    def fail(event):
        raise ValueError("private details")

    failed = MonitorWidget({}, fail)
    failed.event = {"kind": "refresh", "sequence": 2}
    assert failed.response["status"] == "error"
    assert "private details" not in failed.response["message"]
    failed.close()


def test_widget_acknowledges_repeated_actions_individually():
    events = []
    widget = MonitorWidget({}, lambda event: events.append(event))
    for sequence in (1, 2):
        widget.event = {"kind": "refresh", "sequence": sequence}
        assert widget.response == {"status": "ok", "sequence": sequence, "message": ""}
    assert len(events) == 2
    widget.close()


def test_widget_uses_snapshot_locale_messages_for_user_visible_failures():
    snapshot = {
        "messages": {
            "monitor.selection_unavailable": "현재 선택을 사용할 수 없습니다.",
            "monitor.update_failed": "화면을 갱신하지 못했습니다.",
        }
    }
    rejected = MonitorWidget(snapshot, lambda event: False)
    rejected.event = {"kind": "focus", "channel": "missing", "sequence": 1}
    assert rejected.response["message"] == "현재 선택을 사용할 수 없습니다."
    rejected.close()

    def fail(event):
        raise RuntimeError("private details")

    failed = MonitorWidget(snapshot, fail)
    failed.event = {"kind": "refresh", "sequence": 2}
    assert failed.response["message"] == "화면을 갱신하지 못했습니다."
    failed.close()
