"""Schema-dispatched loading for user-facing analysis read models."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from industrial_phm.analysis.projectors.xjtu import (
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
)
from industrial_phm.analysis.view import AnalysisView, AnalysisViewError
from industrial_phm.experiments.result_inspection import (
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


def load_analysis_view(path: Path) -> AnalysisView:
    """Load a supported artifact without leaking schema-specific dispatch to the caller."""
    try:
        inspection = inspect_experiment_result(path)
    except ExperimentResultInspectionError as error:
        raise AnalysisViewError(str(error)) from error

    try:
        projector = _PROJECTORS[inspection.schema_id]
    except KeyError as error:
        raise AnalysisViewError(
            f"analysis view does not support schema {inspection.schema_id!r}"
        ) from error

    return projector(path)
