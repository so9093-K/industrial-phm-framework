"""Supervisor-authorized, nonblocking PHM explanations and existing human review linkage."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

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
from industrial_phm.runtime.operations_web_change_context import (
    OPENS,
    VIEWS,
    analysis_descriptions,
    asset_label,
    change_analyses,
    mentioned_analysis,
    screen_view,
    selected_change,
    view_facts,
)
from industrial_phm.runtime.operations_web_load_comparison import (
    load_comparison_for_answer,
    load_comparison_query,
    read_load_comparison,
)
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
            record = self._parent(parent_id, context)
            context["history"] = [
                {"question": record["context"]["question"], "answer": record["answer"]["summary"]}
            ]
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
        stored = (
            context
            if screen is None
            else {
                key: value
                for key, value in context.items()
                if key
                not in {
                    "history",
                    "load_profile",
                    "compare_load",
                    "load_comparison_result",
                    "analyses",
                    "active_analysis",
                    "record_year",
                }
            }
        )
        identifier = self.store.request(stored, model=provider.model, owner=self.owner)

        def generate() -> None:
            comparison: dict[str, Any] | None = None
            opened: str | None = None
            try:
                if screen is None:
                    answer = generate_grounded_answer(context, provider)
                else:
                    analyses = analysis_descriptions(
                        list(context.get("analyses") or []),
                        vibration=not str(context["binding_id"]).startswith("history:"),
                    )
                    if "load_comparison_result" in context:
                        # 이 대화에서 이미 본 비교는 다시 실행하지 않는다.
                        analyses.pop("compare_same_load", None)
                    if context.get("compare_load"):
                        answer = {"tool": "compare_same_load"}
                    else:
                        answer = generate_change_answer(
                            context | {"screen": screen}, provider, analyses=analyses
                        )
                    chosen = answer.pop("tool", None)
                    if chosen == "compare_same_load" and (plan := context.get("load_profile")):
                        comparison = read_load_comparison(
                            self.workspace, plan["query"], plan["interpretation"]
                        )
                        self.store.publish_comparison(
                            identifier, owner=self.owner, result=comparison
                        )
                        context["load_comparison_result"] = load_comparison_for_answer(comparison)
                    elif chosen is not None and chosen != "compare_same_load":
                        # 고른 분석 화면은 답 아래 링크로 열린다. 링크 이름이 그 화면을 말하므로
                        # 답에 소개 문장을 시키지 않는다(시켰더니 매번 같은 문장이 붙었다).
                        opened = chosen
                        # 그 화면의 수치를 읽을 수 있으면 답이 그 수치로 말한다. 없으면 모델은
                        # '주파수 데이터가 없다'고 답하고 링크만 붙었다.
                        if not context.get("active_analysis") and (
                            numbers := self._opened_numbers(context, OPENS[chosen])
                        ):
                            context["opened_view"] = {f"{VIEWS[OPENS[chosen]]} 화면": numbers}
                    if chosen:
                        answer = generate_change_answer(context | {"screen": screen}, provider)
            except AnalysisExplanationError:
                self.store.finish(
                    identifier,
                    owner=self.owner,
                    error="AI explanation unavailable",
                    answer={"load_comparison": comparison} if comparison is not None else None,
                )
            else:
                text = (answer["summary"] + " " + answer.get("next_step", "")).strip()
                if opened is None and comparison is None and screen is not None:
                    # 말로 권한 화면을 답 아래 링크로 연다.
                    # 정해 둔 후속 링크가 다른 화면을 가리키지 않게 한다.
                    opened = mentioned_analysis(answer["summary"], analyses)
                if comparison is not None:
                    answer = answer | {"load_comparison": comparison}
                if opened is not None:
                    answer = answer | {"analysis": opened}
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

    def _opened_numbers(self, context: dict[str, Any], view: str) -> dict[str, str]:
        """What the analysis the AI opens shows for this change, read as the screen reads it."""
        until = context.get("until")
        vibration = not str(context["binding_id"]).startswith("history:")
        scope = (
            {"acquisition_until" if vibration else "record_until": str(until)}
            if until is not None
            else None
        )
        try:
            change = selected_change(
                self.workspace, context["asset_id"], context["change_id"], scope
            )
            return view_facts(self.workspace, change, view)
        except ValueError, LookupError, OSError:
            # 그 사이 기록이 달라졌으면 수치 없이 답하고 링크만 연다.
            return {}

    def _parent(self, parent_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Read one completed turn from the same selected comparison and conversation."""
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
        return parent

    def _thread(self, parent_id: str, context: dict[str, Any]) -> list[dict[str, str]]:
        """The conversation a change question continues, oldest first.

        A conversation needs what was already said. Each answer is a few sentences, so the
        last ``_TURNS`` turns stay a small request.
        """
        turns: list[dict[str, str]] = []
        current: str | None = parent_id
        while current is not None and len(turns) < _TURNS:
            record = self._parent(current, context)
            turns.insert(
                0,
                {"question": record["context"]["question"], "answer": record["answer"]["summary"]},
            )
            if (
                not context.get("active_analysis")
                and (comparison := record["answer"].get("load_comparison"))
                and comparison["status"] == "ready"
            ):
                context.setdefault("load_comparison_result", load_comparison_for_answer(comparison))
            current = record["context"].get("parent_id")
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
            "analysis",
            "at",
            "view",
            "view_snapshot",
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
    history_change = context.get("history_change")
    if history_change:
        record_start = datetime.fromisoformat(history_change["start"]).astimezone(
            ZoneInfo("Asia/Seoul")
        )
        context["record_year"] = record_start.year
    query = load_comparison_query(context)
    if payload.get("analysis") is not None and (
        payload["analysis"] != "same_load" or query is None
    ):
        raise ValueError("unavailable change analysis")
    if query is not None:
        context["load_profile"] = {
            "query": query,
            "interpretation": context["history_change"]["interpretation_id"],
        }
    if payload.get("analysis") == "same_load":
        context["compare_load"] = True
    analyses = change_analyses(context, same_load=query is not None)
    if (at := payload.get("at")) is not None:
        # 그래프에서 짚은 곳: 전력은 시각(시간대 포함), 진동은 측정 번호.
        text = str(at)
        if len(text) > 64:
            raise ValueError("invalid pointed place")
        if "history_change" in context:
            if datetime.fromisoformat(text).utcoffset() is None:
                raise ValueError("invalid pointed place")
        elif not text.isdigit():
            raise ValueError("invalid pointed place")
        context["at"] = text
    screen: dict[str, Any]
    view = payload.get("view")
    snapshot = payload.get("view_snapshot")
    if view is not None:
        if view not in VIEWS or not isinstance(snapshot, str) or len(snapshot.encode()) > 1800:
            raise ValueError("invalid analysis view")
        values = json.loads(snapshot)
        if (
            not isinstance(values, dict)
            or not 1 <= len(values) <= 8
            or not all(
                isinstance(value, str) and value and 0 < len(key) <= 100 and len(value) <= 220
                for key, value in values.items()
            )
        ):
            raise ValueError("invalid analysis view results")
        name = VIEWS[str(view)]
        context["active_analysis"] = name
        context["answer_view"] = name
        if shown_scope := values.get("조회 범위"):
            context["analysis_scope"] = shown_scope
        context.pop("compare_load", None)
        screen = {"설비": asset_label(workspace, asset), f"지금 보고 있는 {name} 화면": values}
    else:
        if snapshot is not None:
            raise ValueError("analysis view is required for results")
        screen = screen_view(workspace, context)
        context["answer_view"] = "변화 조사"
        if history_change:
            # The overview reads the selected change and other points of the same stored record.
            context["analysis_scope"] = screen["특이사항"]["언제"]
        else:
            change = context["vibration_change"]
            context["analysis_scope"] = f"{change['from']}~{change['to']}번째 측정"
        if "그래프에서 짚은 곳" in screen:
            # 대화에 '어디를 짚고 물었는지'를 함께 보인다.
            context["pointed"] = screen["그래프에서 짚은 곳"]["때"]
    context["analyses"] = (
        [name for name in analyses if OPENS.get(name) != view and name != "compare_same_load"]
        if view is not None
        else list(analyses)
    )
    context.pop("history_change", None)
    context.pop("vibration_change", None)
    context.pop("vibration_current_axes", None)
    context.pop("vibration_last", None)
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
