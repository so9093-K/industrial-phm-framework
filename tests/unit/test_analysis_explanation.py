import json
from pathlib import Path
from typing import Any

import pytest

from industrial_phm.analysis import load_xjtu_lstm_analysis_view
from industrial_phm.genai import (
    AnalysisExplanationError,
    build_analysis_explanation_context,
    generate_openai_analysis_explanation,
    render_analysis_explanation_input,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULT = (
    _REPOSITORY_ROOT
    / "docs"
    / "research"
    / "results"
    / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
)


def test_explanation_context_preserves_recorded_capability_boundaries() -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)

    context = build_analysis_explanation_context(analysis, "Bearing1_2")

    assert context.asset_id == "Bearing1_2"
    assert context.analyzed_window_count == len(analysis.asset("Bearing1_2").observations)
    assert len(context.highest_scores) == 5
    assert tuple(item.score for item in context.highest_scores) == tuple(
        sorted((item.score for item in context.highest_scores), reverse=True)
    )
    assert len(context.top_feature_residuals) == 5
    assert "anomaly-scoring" in context.available_capabilities
    assert "prognostics-rul" in context.unsupported_capabilities
    assert context.source_facts
    assert context.model_facts
    assert context.evaluation_facts
    assert context.provenance_facts


def test_explanation_input_is_structured_and_question_scoped() -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)
    context = build_analysis_explanation_context(analysis, "Bearing2_2")

    rendered = render_analysis_explanation_input(
        context,
        question="이 분석에서 관찰된 가장 큰 변화는 무엇인가요?",
    )
    document = json.loads(rendered)

    assert document["analysis_evidence"]["asset_id"] == "Bearing2_2"
    assert document["user_question"] == "이 분석에서 관찰된 가장 큰 변화는 무엇인가요?"
    assert "prognostics-rul" in document["analysis_evidence"]["unsupported_capabilities"]


def test_explanation_context_rejects_invalid_limit() -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)

    with pytest.raises(AnalysisExplanationError, match="positive integer"):
        build_analysis_explanation_context(analysis, "Bearing1_2", evidence_limit=0)


def test_explanation_input_rejects_blank_question() -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)
    context = build_analysis_explanation_context(analysis, "Bearing1_2")

    with pytest.raises(AnalysisExplanationError, match="trimmed non-empty"):
        render_analysis_explanation_input(context, question=" ")


def test_openai_generator_uses_stateless_responses_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)
    context = build_analysis_explanation_context(analysis, "Bearing3_2")
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
                                    "text": "관찰된 evidence를 기준으로 한 설명입니다.",
                                }
                            ],
                        }
                    ]
                }
            ).encode()

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(
        "industrial_phm.genai.analysis_explanation.urlopen",
        fake_urlopen,
    )

    text = generate_openai_analysis_explanation(
        context,
        api_key="test-secret",
        model="test-model",
        question="무엇을 확인해야 하나요?",
        timeout_seconds=12,
    )

    assert text == "관찰된 evidence를 기준으로 한 설명입니다."
    assert captured["authorization"] == "Bearer test-secret"
    assert captured["timeout"] == 12.0
    body = captured["body"]
    assert body["model"] == "test-model"
    assert body["store"] is False
    assert "test-secret" not in body["input"]
    assert "prognostics-rul" in body["input"]


def test_openai_generator_requires_output_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)
    context = build_analysis_explanation_context(analysis, "Bearing1_2")

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"output": []}'

    monkeypatch.setattr(
        "industrial_phm.genai.analysis_explanation.urlopen",
        lambda request, timeout: FakeResponse(),
    )

    with pytest.raises(AnalysisExplanationError, match="no output text"):
        generate_openai_analysis_explanation(
            context,
            api_key="test-secret",
            model="test-model",
        )
