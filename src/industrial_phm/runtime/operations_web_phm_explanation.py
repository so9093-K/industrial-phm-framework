"""Supervisor-authorized, nonblocking PHM explanations and existing human review linkage."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from industrial_phm.application import JsonFindingReviewRepository, JsonOperationalFindingRepository
from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.operational import OperationalFinding
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import (
    PhmExplanationStore,
    explanation_context,
    operator_explanation_context,
)
from industrial_phm.genai.analysis_explanation import AnalysisExplanationError
from industrial_phm.genai.local_explanation import (
    ExplanationProvider,
    comparison_claim_warnings,
    generate_local_explanation,
    ungrounded_numbers,
    verdict_phrases,
)
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
        provider = ExplanationProvider(
            base_url=os.environ.get("INDUSTRIAL_PHM_GENAI_BASE_URL", "http://127.0.0.1:9400/v1"),
            model=os.environ.get("INDUSTRIAL_PHM_GENAI_MODEL", "local-main"),
            api_key=os.environ.get("INDUSTRIAL_PHM_GENAI_API_KEY"),
            allow_remote=os.environ.get("INDUSTRIAL_PHM_GENAI_ALLOW_REMOTE", "") == "1",
        )
        identifier = self.store.request(context, model=provider.model, owner=self.owner)

        def generate() -> None:
            try:
                text = generate_local_explanation(context, provider)
            except AnalysisExplanationError:
                self.store.finish(identifier, owner=self.owner, error="AI explanation unavailable")
            else:
                grounding_context = operator_explanation_context(context)
                grounding_context.pop("question", None)
                # The model must only restate supplied values; flag any number it invented.
                self.store.finish(
                    identifier,
                    owner=self.owner,
                    text=text,
                    warnings=ungrounded_numbers(text, grounding_context)
                    + verdict_phrases(text)
                    + comparison_claim_warnings(text, grounding_context),
                )

        Thread(target=generate, name="phm-explanation", daemon=True).start()
        return {
            "explanation_id": identifier,
            "status": "pending",
            "binding_id": binding_id,
            "position": position,
        }


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
        binding_id, position, compare_position=compare_position, question=question.strip()
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
