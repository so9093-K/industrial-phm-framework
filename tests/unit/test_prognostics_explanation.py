import json
from pathlib import Path
from typing import Any

import pytest

from industrial_phm.analysis import load_xjtu_lstm_analysis_view, load_xjtu_rul_analysis_view
from industrial_phm.genai import (
    AnalysisExplanationError,
    build_prognostics_explanation_context,
    generate_openai_prognostics_explanation,
    render_prognostics_explanation_input,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"
_ANOMALY_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"


def test_prognostics_context_carries_target_semantics_with_every_estimate() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)

    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    assert context.asset_id == "Bearing1_2"
    assert context.target_unit == "acquisition-interval"
    assert context.endpoint_semantics == "last-recorded-acquisition"
    assert context.target_formula == "N-k"
    assert context.target_is_clipped is False
    assert "acquisition-interval" in context.target_meaning
    assert "last recorded acquisition" in context.target_meaning


def test_prognostics_context_reports_unvalidated_capabilities_as_unavailable() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)

    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    assert context.uncertainty_interval_available is False
    assert context.physical_failure_threshold_validated is False
    assert "prediction-interval" in context.unsupported_capabilities
    assert "validated-physical-failure-threshold" in context.unsupported_capabilities
    assert "prognostics-rul-point-estimate" in context.available_capabilities


def test_prognostics_context_carries_evaluation_scope_and_warnings() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)

    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    assert context.evaluation_scope == "retrospective-development-validation"
    assert context.holdout_test_used is False
    assert context.field_validated is False
    assert any("recorded-end acquisition interval" in item for item in context.evaluation_warnings)
    assert any("holdout test is excluded" in item for item in context.evaluation_warnings)
    assert any("uncertainty intervals" in item for item in context.evaluation_warnings)


def test_prognostics_context_keeps_method_comparison_without_a_primary_method() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)

    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    assert context.primary_method_id is None
    assert len(context.methods) == 3
    assert {method.method_id for method in context.methods} == {
        method.method_id for method in analysis.require_prognostics_evidence().methods
    }


def test_prognostics_context_preserves_recorded_estimates_without_recomputation() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)
    evidence = analysis.require_prognostics_evidence()
    recorded = {
        method.method_id: next(asset for asset in method.assets if asset.asset_id == "Bearing1_2")
        for method in evidence.methods
    }

    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    for method in context.methods:
        asset = recorded[method.method_id]
        assert (
            method.last_recorded_remaining_useful_life == asset.last_recorded_remaining_useful_life
        )
        assert method.last_recorded_acquisition_index == asset.last_recorded_acquisition_index
        assert method.mean_absolute_error == asset.mean_absolute_error
        assert method.normalized_mean_absolute_error == asset.normalized_mean_absolute_error


def test_prognostics_context_keeps_a_negative_estimate_unclipped() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)

    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    negative = [
        method for method in context.methods if method.last_recorded_remaining_useful_life < 0.0
    ]
    assert negative, "this artifact records a negative Ridge estimate for Bearing1_2"
    assert context.target_is_clipped is False


def test_prognostics_context_rejects_an_artifact_without_prognostics_evidence() -> None:
    analysis = load_xjtu_lstm_analysis_view(_ANOMALY_RESULT)

    with pytest.raises(AnalysisExplanationError, match="carries no prognostics evidence"):
        build_prognostics_explanation_context(analysis, "Bearing1_2")


def test_prognostics_context_rejects_an_unknown_asset() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)

    with pytest.raises(AnalysisExplanationError, match="Bearing9_9"):
        build_prognostics_explanation_context(analysis, "Bearing9_9")


def test_rendered_prognostics_input_is_deterministic_and_carries_limits() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)
    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    rendered = render_prognostics_explanation_input(context, question="언제 교체해야 하나요?")

    assert rendered == render_prognostics_explanation_input(
        context,
        question="언제 교체해야 하나요?",
    )
    payload = json.loads(rendered)
    assert payload["user_question"] == "언제 교체해야 하나요?"
    evidence = payload["prognostics_evidence"]
    assert evidence["target_unit"] == "acquisition-interval"
    assert evidence["primary_method_id"] is None
    assert evidence["uncertainty_interval_available"] is False
    assert evidence["physical_failure_threshold_validated"] is False
    assert evidence["evaluation_scope"] == "retrospective-development-validation"
    assert evidence["holdout_test_used"] is False
    assert evidence["field_validated"] is False
    assert evidence["evaluation_warnings"]


def test_rendered_prognostics_input_rejects_an_untrimmed_question() -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)
    context = build_prognostics_explanation_context(analysis, "Bearing1_2")

    with pytest.raises(AnalysisExplanationError, match="trimmed non-empty"):
        render_prognostics_explanation_input(context, question=" 교체 시점 ")


def test_prognostics_generator_sends_rul_boundary_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = load_xjtu_rul_analysis_view(_RUL_RESULT)
    context = build_prognostics_explanation_context(analysis, "Bearing1_2")
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "기록된 추정값을 그대로 설명합니다.",
                                }
                            ],
                        }
                    ]
                }
            ).encode()

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(
        "industrial_phm.genai.analysis_explanation.urlopen",
        fake_urlopen,
    )

    text = generate_openai_prognostics_explanation(
        context,
        api_key="test-secret",
        model="test-model",
    )

    assert text == "기록된 추정값을 그대로 설명합니다."
    body = captured["body"]
    assert body["store"] is False
    instructions = body["instructions"]
    assert "Do not recompute, extrapolate" in instructions
    assert "physical failure time" in instructions
    assert "failure threshold" in instructions
    assert "primary_method_id is null" in instructions
    assert "evaluation_scope" in instructions
    assert "never broaden validation" in instructions
    assert "test-secret" not in body["input"]
