"""Shared XJTU inspection vocabulary and helpers."""

from __future__ import annotations

from collections.abc import Mapping

from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.result_inspection_support import (
    _expect_equal,
    _mapping_field,
    _text_sequence,
)

SCORE_SEMANTICS = "higher-is-more-anomalous"
AVAILABLE_CAPABILITIES = (
    "anomaly-scoring",
    "descriptive-score-trajectory-evaluation",
)
UNSUPPORTED_CAPABILITIES = (
    "thresholded-state-detection",
    "health-assessment",
    "fault-diagnostics",
    "prognostics-rul",
)
LSTM_AVAILABLE_CAPABILITIES = (
    *AVAILABLE_CAPABILITIES,
    "reconstruction-residual-evidence",
)


def validated_capability_scope(
    root: Mapping[str, object],
    expected_available: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Validate one XJTU artifact capability declaration."""
    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(capability, "unsupported_or_not_validated", "capability_scope")
    _expect_equal(available, expected_available, "available capability scope")
    _expect_equal(unsupported, UNSUPPORTED_CAPABILITIES, "unsupported capability scope")
    return available, unsupported


def format_parameters(parameters: Mapping[str, ExperimentParameter]) -> str:
    """Render a deterministic parameter summary for inspection facts."""
    return ", ".join(f"{name}={value!r}" for name, value in sorted(parameters.items()))
