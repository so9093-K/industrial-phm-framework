from pathlib import Path

import pytest

from industrial_phm.analysis import load_xjtu_lstm_analysis_view
from industrial_phm.genai import (
    AnalysisExplanationError,
    build_analysis_explanation_context,
    generate_openai_analysis_explanation,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULT = (
    _REPOSITORY_ROOT
    / "docs"
    / "research"
    / "results"
    / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/v1/responses",
        "https://api.openai.com.evil.example/v1/responses",
        "https://api.openai.com@evil.example/v1/responses",
        "http://api.openai.com/v1/responses",
    ],
)
def test_openai_generator_rejects_untrusted_endpoint(endpoint: str) -> None:
    analysis = load_xjtu_lstm_analysis_view(_RESULT)
    context = build_analysis_explanation_context(analysis, "Bearing1_2")

    with pytest.raises(
        AnalysisExplanationError,
        match="configured OpenAI Responses API endpoint",
    ):
        generate_openai_analysis_explanation(
            context,
            api_key="test-secret",
            model="test-model",
            endpoint=endpoint,
        )
