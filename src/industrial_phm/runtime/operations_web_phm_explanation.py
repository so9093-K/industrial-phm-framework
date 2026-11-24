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
from industrial_phm.genai.change_answer import generate_change_answer
from industrial_phm.genai.local_explanation import AnalysisExplanationError, ExplanationProvider
from industrial_phm.genai.phm_answer import generate_grounded_answer
from industrial_phm.runtime.operations_web_change_context import screen_view, selected_change
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_MANAGERS: dict[Path, ExplanationManager] = {}
_LOCK = Lock()
# 특이사항 대화에서 모델에 함께 넘기는 앞선 문답 수.
_TURNS = 6


def configured_provider() -> ExplanationProvider:
    """The explanation model this workspace's supervisor is configured to ask."""
    return ExplanationProvider(
        base_url=os.environ.get("INDUSTRIAL_PHM_GENAI_BASE_URL", "http://127.0.0.1:9400/v1"),
        model=os.environ.get("INDUSTRIAL_PHM_GENAI_MODEL", "local-main"),
        api_key=os.environ.get("INDUSTRIAL_PHM_GENAI_API_KEY"),
        allow_remote=os.environ.get("INDUSTRIAL_PHM_GENAI_ALLOW_REMOTE", "") == "1",
        timeout_seconds=float(os.environ.get("INDUSTRIAL_PHM_GENAI_TIMEOUT_SECONDS", "120")),
    )


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
        provider = configured_provider()
        return self._enqueue(context, provider)

    def request_change(self, context: dict[str, Any], screen: dict[str, Any]) -> dict[str, object]:
        if parent := context.get("parent_id"):
            context["history"] = self._thread(parent, context)
        return self._enqueue(context, configured_provider(), screen=screen)

    def _enqueue(
        self,
        context: dict[str, Any],
        provider: ExplanationProvider,
        *,
        screen: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        stored = context if screen is None else {k: v for k, v in context.items() if k != "history"}
        identifier = self.store.request(stored, model=provider.model, owner=self.owner)

        def generate() -> None:
            try:
                if screen is None:
                    answer = generate_grounded_answer(context, provider)
                else:
                    answer = generate_change_answer(context | {"screen": screen}, provider)
            except AnalysisExplanationError:
                self.store.finish(identifier, owner=self.owner, error="AI explanation unavailable")
            else:
                text = (answer["summary"] + " " + answer.get("next_step", "")).strip()
                self.store.finish(identifier, owner=self.owner, text=text, answer=answer)

        Thread(target=generate, name="phm-explanation", daemon=True).start()
        return {
            "schema_version": 1,
            "explanation_id": identifier,
            "status": "pending",
            "binding_id": context["binding_id"],
            "position": context["position"],
            **({"change_id": context["change_id"]} if context.get("change_id") else {}),
        }

    def _history(self, parent_id: str, context: dict[str, Any]) -> list[dict[str, str]]:
        """The question and answer this follow-up continues: only that one turn.

        A follow-up such as '그럼 ...' needs the turn it continues, not the whole thread. Longer
        threads made the local model slower and made it copy the answer format instead of answering.
        """
        parent = self.store.get(parent_id)
        same = parent is not None and (
            parent["binding_id"],
            parent["position"],
            parent["context"]["signal_comparison"]["previous_position"],
            parent["context"].get("change_id"),
            parent["context"].get("conversation_id"),
            parent["context"].get("until"),
        ) == (
            context["binding_id"],
            context["position"],
            context["signal_comparison"]["previous_position"],
            context.get("change_id"),
            context.get("conversation_id"),
            context.get("until"),
        )
        if parent is None or not same or parent["status"] != "complete" or not parent["answer"]:
            raise ValueError("follow-up must continue a completed answer of the same comparison")
        return [{"question": parent["context"]["question"], "answer": parent["answer"]["summary"]}]

    def _thread(self, parent_id: str, context: dict[str, Any]) -> list[dict[str, str]]:
        """The conversation a change question continues, oldest first.

        A conversation needs what was already said. Each answer is a few sentences, so the
        last ``_TURNS`` turns stay a small request.
        """
        turns: list[dict[str, str]] = []
        current: str | None = parent_id
        while current is not None and len(turns) < _TURNS:
            turns.insert(0, self._history(current, context)[0])
            record = self.store.get(current)
            current = record["context"].get("parent_id") if record else None
        return turns


def initialize_explanation_manager(root: Path) -> ExplanationManager:
    with _LOCK:
        manager = _MANAGERS.get(root)
        if manager is None:
            manager = ExplanationManager(root)
            _MANAGERS[root] = manager
        return manager


def change_conversation_id(value: str) -> str:
    if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid change conversation")
    return value


def prepare_web_explanation(
    workspace: OperationsWorkspace, payload: dict[str, object]
) -> dict[str, object]:
    """Read the change in the Web process, where the monitoring view is already prepared."""
    if "_change" in payload or "screen" in payload:
        raise ValueError("unexpected explanation fields")
    if "change_id" not in payload:
        return payload
    if (
        not {"asset_id", "change_id", "question", "conversation_id"}
        <= set(payload)
        <= {
            "asset_id",
            "change_id",
            "question",
            "conversation_id",
            "parent_id",
            "record_until",
            "acquisition_until",
        }
    ):
        raise ValueError("unexpected change explanation fields")
    if not all(isinstance(value, str) for value in payload.values()):
        raise ValueError("invalid change question")
    conversation = change_conversation_id(str(payload["conversation_id"]))
    asset, key, change_question = (
        str(payload["asset_id"]),
        str(payload["change_id"]),
        str(payload["question"]).strip(),
    )
    if (
        not asset
        or len(asset) > 512
        or len(key) != 64
        or any(c not in "0123456789abcdef" for c in key)
        or not 1 <= len(change_question) <= 600
    ):
        raise ValueError("invalid selected change or question")
    parent = payload.get("parent_id")
    if parent is not None and len(str(parent)) > 128:
        raise ValueError("invalid follow-up")
    scope: dict[str, str] = {
        k: str(payload[k]) for k in ("record_until", "acquisition_until") if k in payload
    }
    context = selected_change(workspace, asset, key, scope)
    screen = screen_view(workspace, context)
    context.pop("history_change", None)
    context.pop("vibration_change", None)
    context["question"] = change_question
    context["conversation_id"] = conversation
    if parent:
        context["parent_id"] = parent
    return {"_change": context, "screen": screen}


def request_phm_explanation(root: Path, payload: dict[str, object]) -> dict[str, object]:
    if "change_id" in payload:
        payload = prepare_web_explanation(OperationsWorkspace(root), payload)
    if set(payload) == {"_change", "screen"}:
        # Only the authenticated Web child constructs this command. The HTTP handler rejects
        # those fields in browser requests before forwarding a command to the supervisor.
        context, screen = payload["_change"], payload["screen"]
        if not isinstance(context, dict) or not isinstance(screen, dict):
            raise ValueError("invalid prepared change")
        return initialize_explanation_manager(root).request_change(context, screen)
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
        "schema_version": 1,
        "finding_id": finding.finding_id,
        "explanation_id": identifier,
        "status": status.value,
        "analysis_run_id": run_id,
        "meaning": "human-review-not-maintenance-or-diagnosis",
    }
