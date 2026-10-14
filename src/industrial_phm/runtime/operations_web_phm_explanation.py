"""Supervisor-authorized, nonblocking PHM explanations and existing human review linkage."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from industrial_phm.application import JsonFindingReviewRepository, JsonOperationalFindingRepository
from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.operational import OperationalFinding
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import PhmExplanationStore, explanation_context
from industrial_phm.application.phm_range import focus_point
from industrial_phm.genai.analysis_explanation import AnalysisExplanationError
from industrial_phm.genai.local_explanation import ExplanationProvider
from industrial_phm.genai.phm_answer import generate_grounded_answer
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_MANAGERS: dict[Path, ExplanationManager] = {}
_LOCK = Lock()


class ExplanationManager:
    def __init__(self, root: Path) -> None:
        self.workspace = OperationsWorkspace(root)
        self.owner = uuid4().hex
        self.store = PhmExplanationStore(self.workspace.phm_explanation_path)
        self.store.recover(self.owner)

    def request(
        self,
        binding_id: str,
        position: int,
        *,
        compare_position: int | None = None,
        question: str = "이전 시점과 비교해 어떤 측정 신호가 함께 변했는지 설명해 주세요.",
        parent_id: str | None = None,
        focus_position: int | None = None,
        focus_series: str | None = None,
    ) -> dict[str, object]:
        workspace = self.workspace
        context = explanation_context(
            SqlitePhmAnalysisStore(workspace.phm_analysis_path),
            workspace.models_path,
            SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
            binding_id,
            position,
            compare_position=compare_position,
            question=question,
            windows=SqliteObservationWindowRepository(workspace.window_state_path),
        )
        if parent_id is not None:
            context["parent_id"] = parent_id
            context["history"] = self._history(parent_id, context)
        if focus_position is not None:
            span = context["signal_comparison"].get("range")
            if not span:
                raise ValueError("focus needs a selected comparison range")
            store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
            binding = next(b for b in store.list_bindings() if b.binding_id == binding_id)
            context["focus"] = focus_point(
                store,
                binding_id,
                binding.step_kind,
                span,
                focus_position,
                list(span["features"]),
                series=focus_series,
            )
        provider = ExplanationProvider(
            base_url=os.environ.get("INDUSTRIAL_PHM_GENAI_BASE_URL", "http://127.0.0.1:9400/v1"),
            model=os.environ.get("INDUSTRIAL_PHM_GENAI_MODEL", "local-main"),
            api_key=os.environ.get("INDUSTRIAL_PHM_GENAI_API_KEY"),
            allow_remote=os.environ.get("INDUSTRIAL_PHM_GENAI_ALLOW_REMOTE", "") == "1",
        )
        identifier = self.store.request(context, model=provider.model, owner=self.owner)

        def generate() -> None:
            try:
                answer = generate_grounded_answer(context, provider)
            except AnalysisExplanationError:
                self.store.finish(identifier, owner=self.owner, error="AI explanation unavailable")
            else:
                # Every reference in the answer was checked against the stored comparison.
                text = (answer["summary"] + " " + answer["next_step"]).strip()
                self.store.finish(identifier, owner=self.owner, text=text, answer=answer)

        Thread(target=generate, name="phm-explanation", daemon=True).start()
        return {
            "explanation_id": identifier,
            "status": "pending",
            "binding_id": binding_id,
            "position": position,
        }

    def _history(self, parent_id: str, context: dict[str, Any]) -> list[dict[str, str]]:
        """Earlier questions and answers of the same comparison, oldest first, at most three."""
        parent = self.store.get(parent_id)
        same = parent is not None and (
            parent["binding_id"],
            parent["position"],
            parent["context"]["signal_comparison"]["previous_position"],
        ) == (
            context["binding_id"],
            context["position"],
            context["signal_comparison"]["previous_position"],
        )
        if parent is None or not same or parent["status"] != "complete" or not parent["answer"]:
            raise ValueError("follow-up must continue a completed answer of the same comparison")
        earlier = list(parent["context"].get("history") or [])
        earlier.append(
            {"question": parent["context"]["question"], "answer": parent["answer"]["summary"]}
        )
        return earlier[-3:]


def initialize_explanation_manager(root: Path) -> ExplanationManager:
    with _LOCK:
        manager = _MANAGERS.get(root)
        if manager is None:
            manager = ExplanationManager(root)
            _MANAGERS[root] = manager
        return manager


def request_phm_explanation(root: Path, payload: dict[str, object]) -> dict[str, object]:
    if not {"binding_id", "position"} <= set(payload) or set(payload) - {
        "binding_id",
        "position",
        "compare_position",
        "question",
        "parent_id",
        "focus_position",
        "focus_series",
    }:
        raise ValueError("unexpected explanation fields")
    binding_id, position = payload["binding_id"], payload["position"]
    if (
        not isinstance(binding_id, str)
        or not 1 <= len(binding_id) <= 512
        or isinstance(position, bool)
        or not isinstance(position, int)
    ):
        raise ValueError("invalid explanation selection")
    compare_position = payload.get("compare_position")
    parent_id = payload.get("parent_id")
    if parent_id is not None and (not isinstance(parent_id, str) or len(parent_id) > 128):
        raise ValueError("invalid follow-up")
    focus_position = payload.get("focus_position")
    focus_series = payload.get("focus_series")
    if focus_series is not None and (
        not isinstance(focus_series, str) or focus_position is None or len(focus_series) > 512
    ):
        raise ValueError("invalid focus series")
    if focus_position is not None and (
        isinstance(focus_position, bool) or not isinstance(focus_position, int)
    ):
        raise ValueError("invalid focus point")
    question = payload.get(
        "question", "이전 시점과 비교해 어떤 측정 신호가 함께 변했는지 설명해 주세요."
    )
    if (
        (
            compare_position is not None
            and (isinstance(compare_position, bool) or not isinstance(compare_position, int))
        )
        or not isinstance(question, str)
        or not 1 <= len(question.strip()) <= 600
    ):
        raise ValueError("invalid analysis question or comparison")
    return initialize_explanation_manager(root).request(
        binding_id,
        position,
        compare_position=compare_position,
        question=question.strip(),
        parent_id=parent_id,
        focus_position=focus_position,
        focus_series=focus_series,
    )


def request_phm_review(root: Path, payload: dict[str, object]) -> dict[str, object]:
    if set(payload) != {"binding_id", "position", "explanation_id"}:
        raise ValueError("invalid PHM review fields")
    binding_id, position, identifier = (
        payload["binding_id"],
        payload["position"],
        payload["explanation_id"],
    )
    if (
        not isinstance(binding_id, str)
        or isinstance(position, bool)
        or not isinstance(position, int)
    ):
        raise ValueError("invalid PHM review selection")
    workspace = OperationsWorkspace(root)
    explanations = PhmExplanationStore(workspace.phm_explanation_path)
    context = explanation_context(
        SqlitePhmAnalysisStore(workspace.phm_analysis_path),
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        binding_id,
        position,
        include_signals=False,
    )
    record = None
    if identifier is not None:
        if not isinstance(identifier, str):
            raise ValueError("invalid explanation identity")
        record = explanations.get(identifier)
        if (
            record is None
            or record["status"] != "complete"
            or (record["binding_id"], record["position"], record["analysis_run_id"])
            != (binding_id, position, context["analysis_run_id"])
        ):
            raise ValueError("explanation does not match reviewed analysis")
    run_id = context["analysis_run_id"]
    finding = OperationalFinding(
        finding_id="finding-phm-" + run_id,
        analysis_run_id=run_id,
        asset_id=context["asset_id"],
        measurement_point_id=context["measurement_point_id"],
        observed_at=datetime.fromisoformat(context["event_start"] or context["processed_at"]),
        capability_id="phm-" + context["output"]["task"],
        finding_semantics_id="phm-human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=("phm-result-" + run_id,),
    )
    JsonOperationalFindingRepository(workspace.finding_state_path).record(finding)
    if record is not None:
        explanations.link_finding(record["id"], finding.finding_id)
    status = JsonFindingReviewRepository(workspace.maintenance_review_state_path).status_for(
        finding.finding_id
    )
    return {
        "finding_id": finding.finding_id,
        "explanation_id": identifier,
        "status": status.value,
        "analysis_run_id": run_id,
        "meaning": "human-review-not-maintenance-or-diagnosis",
    }
