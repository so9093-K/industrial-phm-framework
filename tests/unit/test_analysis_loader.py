from pathlib import Path

import pytest

from industrial_phm.analysis import AnalysisViewError
from industrial_phm.analysis.loader import load_analysis_surface, load_analysis_view

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_XJTU_LSTM_RESULT = _RESULTS / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
_XJTU_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"
_XJTU_HOLDOUT_RESULT = _RESULTS / "xjtu-sy-iforest-fold-1-holdout-v1.json"
_IMS_RESULT = _RESULTS / "ims-bearings-iforest-single-channel-cross-test-v1.json"
_MIMII_RESULT = _RESULTS / "mimii-due-iforest-domain-shift-development-v1.json"


def test_dispatches_supported_analysis_artifacts_by_schema() -> None:
    anomaly = load_analysis_view(_XJTU_LSTM_RESULT)
    prognostics = load_analysis_view(_XJTU_RUL_RESULT)

    assert anomaly.schema_id == "xjtu-lstm-development-result-v1"
    assert anomaly.anomaly_evidence is not None
    assert anomaly.prognostics_evidence is None
    assert prognostics.schema_id == "xjtu-rul-three-model-validation-result-v1"
    assert prognostics.prognostics_evidence is not None
    assert prognostics.anomaly_evidence is None


def test_rejects_validated_schema_without_analysis_projector() -> None:
    with pytest.raises(AnalysisViewError, match="analysis view does not support schema"):
        load_analysis_view(_XJTU_HOLDOUT_RESULT)

@pytest.mark.parametrize(
    ("artifact", "schema_id"),
    [
        (_XJTU_HOLDOUT_RESULT, "xjtu-fold-1-holdout-result-v1"),
        (_IMS_RESULT, "ims-single-channel-cross-test-result-v1"),
        (_MIMII_RESULT, "mimii-due-domain-shift-development-result-v1"),
    ],
)
def test_surface_keeps_inspection_when_detailed_projector_is_unavailable(
    artifact: Path,
    schema_id: str,
) -> None:
    surface = load_analysis_surface(artifact)

    assert surface.artifact_path == artifact
    assert surface.inspection.schema_id == schema_id
    assert surface.analysis is None
    assert surface.has_detailed_analysis is False


def test_surface_includes_detailed_analysis_when_projector_exists() -> None:
    surface = load_analysis_surface(_XJTU_LSTM_RESULT)

    assert surface.inspection.schema_id == "xjtu-lstm-development-result-v1"
    assert surface.analysis is not None
    assert surface.analysis.anomaly_evidence is not None
    assert surface.has_detailed_analysis is True

