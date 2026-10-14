from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import (
    explanation_context,
    operator_explanation_context,
)
from industrial_phm.runtime.operations_web_phm_explanation import request_phm_explanation
from tests.support.phm import analyze, deliver, phm_workspace


def test_selected_comparison_uses_real_input_and_matching_models_without_modifying_results(
    tmp_path: Path,
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for i, scale in enumerate((0.5, 0.6, 3.0), 1):
        deliver(workspace, tmp_path / "waves", i, scale)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    before = store.list_results("anomaly-a")
    context = explanation_context(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        "anomaly-a",
        3,
        compare_position=1,
        question="어느 진동이 달라졌나요?",
    )
    sent = operator_explanation_context(context)
    comparison = sent["signal_comparison"]
    rms = next(
        row
        for row in comparison["features"]
        if row["feature"].endswith("Horizontal_vibration_signals.rms")
    )
    assert rms["current"] > rms["previous"]
    assert rms["change"] == pytest.approx(rms["current"] - rms["previous"])
    assert comparison["previous_position"] == 1
    assert comparison["original_current"]["sample_count"] == 64
    assert comparison["original_current"]["channels"][0]["rms"] == pytest.approx(rms["current"])
    assert comparison["original_current"]["channels"][0]["unit"] is None
    assert sent["related_models"][0]["binding_id"] == "rul-a"
    assert (
        sent["related_models"][0]["previous_output"]["estimate"]
        > sent["related_models"][0]["output"]["estimate"]
    )
    assert sent["question"] == "어느 진동이 달라졌나요?"
    assert store.list_results("anomaly-a") == before
    rul = explanation_context(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        "rul-a",
        3,
        compare_position=1,
    )
    assert "change_from_previous" in rul["output"]
    assert "change_from_previous" not in operator_explanation_context(rul)["output"]
    assert rul["signal_comparison"]["output_changes"]["estimate"] == pytest.approx(
        rul["output"]["estimate"] - rul["signal_comparison"]["previous_output"]["estimate"]
    )

    # Changed bytes cannot masquerade as the original input even though model features remain.
    (tmp_path / "waves" / "3.csv").write_text("changed")
    changed = explanation_context(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        "anomaly-a",
        3,
    )
    assert not changed["signal_comparison"]["original_current"]["available"]
    assert changed["features"] == context["features"]


@pytest.mark.parametrize("position", [3, 4, 99, -1])
def test_comparison_refuses_missing_or_non_earlier_results(tmp_path: Path, position: int) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for i in range(1, 4):
        deliver(workspace, tmp_path / "waves", i, 0.5)
    analyze(workspace)
    with pytest.raises(ValueError, match="earlier analyzed"):
        explanation_context(
            SqlitePhmAnalysisStore(workspace.phm_analysis_path),
            workspace.models_path,
            SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
            "anomaly-a",
            3,
            compare_position=position,
        )


def test_related_model_requires_same_input_digest_not_only_same_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for i in range(1, 4):
        deliver(workspace, tmp_path / "waves", i, 0.5)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    get = store.get_result

    def different_digest(binding: str, position: int):
        result = get(binding, position)
        if binding == "rul-a" and result is not None:
            return replace(
                result, input_reference={**result.input_reference, "sha256": "different"}
            )
        return result

    monkeypatch.setattr(store, "get_result", different_digest)
    context = explanation_context(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        "anomaly-a",
        3,
    )
    assert context["related_models"] == []


@pytest.mark.parametrize(
    "extra",
    [
        {"question": " "},
        {"question": "x" * 601},
        {"question": 42},
        {"compare_position": True},
        {"compare_position": "1"},
        {"unexpected": 1},
    ],
)
def test_request_rejects_invalid_question_without_starting_a_job(
    tmp_path: Path, extra: dict
) -> None:
    with pytest.raises(ValueError):
        request_phm_explanation(tmp_path, {"binding_id": "anomaly-a", "position": 3, **extra})
    assert not (tmp_path / "phm-explanations.sqlite").exists()
