"""Dataset-specific AnalysisView projectors."""

from industrial_phm.analysis.projectors.xjtu import (
    load_xjtu_lstm_analysis_view,
    load_xjtu_rul_analysis_view,
)

__all__ = [
    "load_xjtu_lstm_analysis_view",
    "load_xjtu_rul_analysis_view",
]
