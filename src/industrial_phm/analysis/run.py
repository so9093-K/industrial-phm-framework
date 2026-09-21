"""Application use case that connects prepared sensor source to an AnalysisView."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from industrial_phm.analysis.view import AnalysisView, AnalysisViewError, load_xjtu_lstm_analysis_view
from industrial_phm.experiments.xjtu_lstm_result import run_xjtu_lstm_development_evaluation


class AnalysisRunError(RuntimeError):
    """Raised when a user-facing analysis execution cannot complete."""


@dataclass(frozen=True, slots=True)
class XjtuLstmAnalysisRun:
    """One completed XJTU LSTM retrospective analysis execution."""

    source: Path
    result_path: Path
    analysis: AnalysisView


def run_xjtu_lstm_analysis_from_source(
    source: Path,
    result_path: Path,
    *,
    code_revision: str,
) -> XjtuLstmAnalysisRun:
    """Run the existing frozen XJTU LSTM path and return its validated presentation view.

    This is an application orchestration boundary, not a new numerical pipeline. It preserves
    the retrospective development semantics of the underlying experiment and immediately
    validates the generated artifact through the same AnalysisView used by the user surface.
    """
    try:
        run_xjtu_lstm_development_evaluation(
            source,
            result_path,
            code_revision=code_revision,
        )
    except (OSError, ValueError) as error:
        raise AnalysisRunError(f"XJTU LSTM analysis execution failed: {error}") from error

    try:
        analysis = load_xjtu_lstm_analysis_view(result_path)
    except (OSError, AnalysisViewError) as error:
        raise AnalysisRunError(
            f"generated XJTU LSTM result could not be loaded as an analysis view: {error}"
        ) from error

    return XjtuLstmAnalysisRun(
        source=source,
        result_path=result_path,
        analysis=analysis,
    )
