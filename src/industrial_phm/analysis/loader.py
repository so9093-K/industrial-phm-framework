"""Schema-dispatched loading for user-facing analysis read models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from industrial_phm.analysis.projectors.xjtu import (
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
)
from industrial_phm.analysis.view import AnalysisView, AnalysisViewError
from industrial_phm.experiments.result_inspection import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    inspect_experiment_result,
)
from industrial_phm.experiments.xjtu_lstm_result import (
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
)

_AnalysisViewProjector = Callable[[Path], AnalysisView]

_PROJECTORS: dict[str, _AnalysisViewProjector] = {
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID: load_xjtu_lstm_analysis_view,
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID: load_xjtu_rul_analysis_view,
}


@dataclass(frozen=True, slots=True)
class AnalysisSurface:
    """One inspectable artifact with optional detailed analysis evidence."""

    artifact_path: Path
    inspection: ExperimentInspection
    analysis: AnalysisView | None

    @property
    def has_detailed_analysis(self) -> bool:
        """Return whether a schema-specific AnalysisView projector is available."""
        return self.analysis is not None


def load_analysis_surface(path: Path) -> AnalysisSurface:
    """Load any inspectable artifact without inventing evidence missing from its schema."""
    try:
        inspection = inspect_experiment_result(path)
    except ExperimentResultInspectionError as error:
        raise AnalysisViewError(str(error)) from error

    projector = _PROJECTORS.get(inspection.schema_id)
    analysis = None if projector is None else projector(path)
    return AnalysisSurface(
        artifact_path=path,
        inspection=inspection,
        analysis=analysis,
    )


def load_analysis_view(path: Path) -> AnalysisView:
    """Load an artifact that has a schema-specific detailed analysis projector."""
    surface = load_analysis_surface(path)
    if surface.analysis is None:
        raise AnalysisViewError(
            f"analysis view does not support schema {surface.inspection.schema_id!r}"
        )
    return surface.analysis
