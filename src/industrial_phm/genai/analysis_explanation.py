"""Generative-AI explanation over validated PHM analysis evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from industrial_phm.analysis import (
    AnalysisView,
    AnalysisViewError,
    summarize_prognostics_for_asset,
)
from industrial_phm.experiments import InspectionStage

_OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
_EXPLANATION_INSTRUCTIONS = (
    "Explain only the provided PHM evidence. Separate observed evidence, model interpretation, "
    "and limits. Never invent fault diagnosis, root cause, alarm/state, maintenance priority, "
    "health indicator, or RUL unless that capability is explicitly available. "
    "State unsupported conclusions as unavailable."
)
_PROGNOSTICS_INSTRUCTIONS = (
    "Explain only the provided remaining-useful-life evidence. Do not recompute, extrapolate, "
    "or convert the recorded estimates: report every number in the provided unit and never "
    "translate one into a calendar date, a clock duration, or a physical failure time. "
    "Describe what one predicted unit means using target_meaning exactly as provided. "
    "Never introduce a failure threshold, alarm or state, maintenance deadline, or confidence "
    "interval unless the evidence marks that capability as available; state each unavailable "
    "capability as unavailable. When primary_method_id is null, present the methods as "
    "development comparison evidence and do not select one as the operational answer. "
    "When the target is not clipped, report a negative estimate as recorded rather than "
    "raising it to zero or calling it a past failure. Respect evaluation_scope, "
    "holdout_test_used, field_validated, and evaluation_warnings exactly as provided; "
    "never broaden validation beyond the recorded population."
)


class AnalysisExplanationError(RuntimeError):
    """Raised when analysis explanation input or generation fails."""


@dataclass(frozen=True, slots=True)
class RankedScoreEvidence:
    """One recorded high-score observation included in explanation context."""

    acquisition_index: int
    source_observation_id: str
    score: float


@dataclass(frozen=True, slots=True)
class RankedFeatureEvidence:
    """One recorded aggregate feature residual included in explanation context."""

    feature_name: str
    mean_squared_residual: float


@dataclass(frozen=True, slots=True)
class AnalysisExplanationContext:
    """Structured evidence sent to a generative model for explanation."""

    asset_id: str
    evidence_class: str
    score_semantics_id: str
    score_direction: str
    analyzed_window_count: int
    acquisition_order_spearman_rho: float
    late_vs_middle_rank_probability: float
    highest_scores: tuple[RankedScoreEvidence, ...]
    top_feature_residuals: tuple[RankedFeatureEvidence, ...]
    available_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    source_facts: tuple[tuple[str, str], ...]
    model_facts: tuple[tuple[str, str], ...]
    evaluation_facts: tuple[tuple[str, str], ...]
    provenance_facts: tuple[tuple[str, str], ...]


def build_analysis_explanation_context(
    analysis: AnalysisView,
    asset_id: str,
    *,
    evidence_limit: int = 5,
) -> AnalysisExplanationContext:
    """Build bounded structured context without recomputing numerical PHM evidence."""
    if (
        isinstance(evidence_limit, bool)
        or not isinstance(evidence_limit, int)
        or evidence_limit <= 0
    ):
        raise AnalysisExplanationError("evidence_limit must be a positive integer")

    anomaly = analysis.require_anomaly_evidence()
    asset = anomaly.asset(asset_id)
    highest_scores = tuple(
        RankedScoreEvidence(
            acquisition_index=observation.acquisition_index,
            source_observation_id=observation.source_observation_id,
            score=observation.score,
        )
        for observation in sorted(
            asset.observations,
            key=lambda observation: observation.score,
            reverse=True,
        )[:evidence_limit]
    )
    top_feature_residuals = tuple(
        RankedFeatureEvidence(feature_name=feature_name, mean_squared_residual=residual)
        for feature_name, residual in sorted(
            zip(anomaly.feature_names, asset.mean_feature_residuals, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )[:evidence_limit]
    )
    stage_by_name = {stage.name: stage for stage in analysis.inspection.stages}
    return AnalysisExplanationContext(
        asset_id=asset.asset_id,
        evidence_class=analysis.evidence_class,
        score_semantics_id=anomaly.score_semantics_id,
        score_direction=anomaly.score_direction,
        analyzed_window_count=asset.score_window_count,
        acquisition_order_spearman_rho=asset.acquisition_order_spearman_rho,
        late_vs_middle_rank_probability=asset.late_vs_middle_rank_probability,
        highest_scores=highest_scores,
        top_feature_residuals=top_feature_residuals,
        available_capabilities=analysis.available_capabilities,
        unsupported_capabilities=analysis.unsupported_capabilities,
        source_facts=_stage_facts(stage_by_name["Source"]),
        model_facts=_stage_facts(stage_by_name["Model"]),
        evaluation_facts=_stage_facts(stage_by_name["Evaluation"]),
        provenance_facts=_stage_facts(stage_by_name["Provenance"]),
    )


def render_analysis_explanation_input(
    context: AnalysisExplanationContext,
    *,
    question: str | None = None,
) -> str:
    """Render deterministic model input from one structured analysis context."""
    _validate_question(question)
    payload: dict[str, object] = {
        "task": (
            "Explain this PHM analysis to a user. Use the recorded evidence and capability "
            "boundaries exactly as provided."
        ),
        "analysis_evidence": asdict(context),
    }
    if question is not None:
        payload["user_question"] = question
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def generate_openai_analysis_explanation(
    context: AnalysisExplanationContext,
    *,
    api_key: str,
    model: str,
    question: str | None = None,
    endpoint: str = _OPENAI_RESPONSES_ENDPOINT,
    timeout_seconds: float = 30.0,
) -> str:
    """Generate one stateless explanation with the OpenAI Responses API."""
    return _post_openai_response(
        render_analysis_explanation_input(context, question=question),
        instructions=_EXPLANATION_INSTRUCTIONS,
        api_key=api_key,
        model=model,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
    )


@dataclass(frozen=True, slots=True)
class PrognosticsMethodComparison:
    """One compared method's recorded estimate and validation error for one asset."""

    method_id: str
    kind: str
    last_recorded_acquisition_index: int
    last_recorded_remaining_useful_life: float
    prediction_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_signed_error: float
    normalized_mean_absolute_error: float


@dataclass(frozen=True, slots=True)
class PrognosticsExplanationContext:
    """Structured remaining-useful-life evidence sent to a generative model.

    Every field is read back from a validated artifact. Target semantics, support definition,
    and unavailable capabilities travel with the numbers so the estimates cannot be presented
    as a validated physical failure time.
    """

    asset_id: str
    evidence_class: str
    target_definition_id: str
    target_unit: str
    target_meaning: str
    target_formula: str
    endpoint_semantics: str
    prediction_alignment: str
    target_is_clipped: bool
    support_definition: str
    support_first_acquisition: int
    support_prediction_count: int
    methods: tuple[PrognosticsMethodComparison, ...]
    primary_method_id: str | None
    uncertainty_interval_available: bool
    physical_failure_threshold_validated: bool
    evaluation_scope: str
    holdout_test_used: bool
    field_validated: bool
    evaluation_warnings: tuple[str, ...]
    available_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    source_facts: tuple[tuple[str, str], ...]
    model_facts: tuple[tuple[str, str], ...]
    evaluation_facts: tuple[tuple[str, str], ...]
    provenance_facts: tuple[tuple[str, str], ...]


def build_prognostics_explanation_context(
    analysis: AnalysisView,
    asset_id: str,
) -> PrognosticsExplanationContext:
    """Build structured RUL context without recomputing any recorded estimate."""
    try:
        summary = summarize_prognostics_for_asset(analysis, asset_id)
    except AnalysisViewError as error:
        raise AnalysisExplanationError(str(error)) from error

    stage_by_name = {stage.name: stage for stage in analysis.inspection.stages}
    return PrognosticsExplanationContext(
        asset_id=summary.asset_id,
        evidence_class=summary.evidence_class,
        target_definition_id=summary.target_definition_id,
        target_unit=summary.target_unit,
        target_meaning=summary.target_description,
        target_formula=summary.target_formula,
        endpoint_semantics=summary.endpoint_semantics,
        prediction_alignment=summary.prediction_alignment,
        target_is_clipped=summary.target_is_clipped,
        support_definition=summary.support_definition,
        support_first_acquisition=summary.support_first_acquisition,
        support_prediction_count=summary.support_prediction_count,
        methods=tuple(
            PrognosticsMethodComparison(
                method_id=row.method_id,
                kind=row.kind,
                last_recorded_acquisition_index=row.last_recorded_acquisition_index,
                last_recorded_remaining_useful_life=row.last_recorded_remaining_useful_life,
                prediction_count=row.prediction_count,
                mean_absolute_error=row.mean_absolute_error,
                root_mean_squared_error=row.root_mean_squared_error,
                mean_signed_error=row.mean_signed_error,
                normalized_mean_absolute_error=row.normalized_mean_absolute_error,
            )
            for row in summary.methods
        ),
        primary_method_id=summary.primary_method_id,
        uncertainty_interval_available=summary.uncertainty_interval_available,
        physical_failure_threshold_validated=summary.physical_failure_threshold_validated,
        evaluation_scope="retrospective-development-validation",
        holdout_test_used=False,
        field_validated=False,
        evaluation_warnings=(
            *_stage_warnings(stage_by_name["Scoring"]),
            *_stage_warnings(stage_by_name["Evaluation"]),
        ),
        available_capabilities=analysis.available_capabilities,
        unsupported_capabilities=analysis.unsupported_capabilities,
        source_facts=_stage_facts(stage_by_name["Source"]),
        model_facts=_stage_facts(stage_by_name["Model"]),
        evaluation_facts=_stage_facts(stage_by_name["Evaluation"]),
        provenance_facts=_stage_facts(stage_by_name["Provenance"]),
    )


def render_prognostics_explanation_input(
    context: PrognosticsExplanationContext,
    *,
    question: str | None = None,
) -> str:
    """Render deterministic model input from one structured prognostics context."""
    _validate_question(question)
    payload: dict[str, object] = {
        "task": (
            "Explain this remaining-useful-life evidence to a user. Use the recorded "
            "estimates, target semantics, and capability boundaries exactly as provided."
        ),
        "prognostics_evidence": asdict(context),
    }
    if question is not None:
        payload["user_question"] = question
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def generate_openai_prognostics_explanation(
    context: PrognosticsExplanationContext,
    *,
    api_key: str,
    model: str,
    question: str | None = None,
    endpoint: str = _OPENAI_RESPONSES_ENDPOINT,
    timeout_seconds: float = 30.0,
) -> str:
    """Generate one stateless RUL explanation with the OpenAI Responses API."""
    return _post_openai_response(
        render_prognostics_explanation_input(context, question=question),
        instructions=_PROGNOSTICS_INSTRUCTIONS,
        api_key=api_key,
        model=model,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
    )


def _post_openai_response(
    rendered_input: str,
    *,
    instructions: str,
    api_key: str,
    model: str,
    endpoint: str,
    timeout_seconds: float,
) -> str:
    """Send one stateless Responses API request and return its output text."""
    _validate_secret(api_key, "api_key")
    _validate_text(model, "model")
    _validate_text(endpoint, "endpoint")
    if not isinstance(timeout_seconds, int | float) or isinstance(timeout_seconds, bool):
        raise AnalysisExplanationError("timeout_seconds must be numerical")
    if timeout_seconds <= 0:
        raise AnalysisExplanationError("timeout_seconds must be positive")

    request_body = json.dumps(
        {
            "model": model,
            "store": False,
            "instructions": instructions,
            "input": rendered_input,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=float(timeout_seconds)) as response:
            payload = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AnalysisExplanationError(
            f"OpenAI Responses API returned HTTP {error.code}: {detail}"
        ) from error
    except URLError as error:
        raise AnalysisExplanationError(
            f"OpenAI Responses API request failed: {error.reason}"
        ) from error

    try:
        document = cast(object, json.loads(payload))
    except json.JSONDecodeError as error:
        raise AnalysisExplanationError("OpenAI Responses API returned invalid JSON") from error
    return _response_output_text(document)


def _response_output_text(document: object) -> str:
    if not isinstance(document, dict):
        raise AnalysisExplanationError("OpenAI Responses API response must be a JSON object")
    output = document.get("output")
    if not isinstance(output, list):
        raise AnalysisExplanationError("OpenAI Responses API response requires output items")

    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise AnalysisExplanationError("OpenAI Responses API response contained no output text")
    return "\n".join(texts)


def _stage_warnings(stage: InspectionStage) -> tuple[str, ...]:
    warnings = getattr(stage, "warnings", ())
    return tuple(str(warning) for warning in warnings)


def _stage_facts(stage: InspectionStage) -> tuple[tuple[str, str], ...]:
    facts = getattr(stage, "facts", ())
    return tuple((str(fact.label), str(fact.value)) for fact in facts)


def _validate_question(question: str | None) -> None:
    if question is not None and (not question.strip() or question != question.strip()):
        raise AnalysisExplanationError("question must be a trimmed non-empty string when provided")


def _validate_secret(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisExplanationError(f"{field_name} must be a non-empty string")


def _validate_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AnalysisExplanationError(f"{field_name} must be a trimmed non-empty string")
