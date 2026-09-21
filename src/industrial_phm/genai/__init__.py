"""Generative-AI explanation services for validated PHM analysis."""

from industrial_phm.genai.analysis_explanation import (
    AnalysisExplanationContext,
    AnalysisExplanationError,
    PrognosticsExplanationContext,
    PrognosticsMethodComparison,
    RankedFeatureEvidence,
    RankedScoreEvidence,
    build_analysis_explanation_context,
    build_prognostics_explanation_context,
    generate_openai_analysis_explanation,
    generate_openai_prognostics_explanation,
    render_analysis_explanation_input,
    render_prognostics_explanation_input,
)

__all__ = [
    "AnalysisExplanationContext",
    "AnalysisExplanationError",
    "PrognosticsExplanationContext",
    "PrognosticsMethodComparison",
    "RankedFeatureEvidence",
    "RankedScoreEvidence",
    "build_analysis_explanation_context",
    "build_prognostics_explanation_context",
    "generate_openai_analysis_explanation",
    "generate_openai_prognostics_explanation",
    "render_analysis_explanation_input",
    "render_prognostics_explanation_input",
]
