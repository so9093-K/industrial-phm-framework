"""Capability-specific analysis presentation helpers for Operations."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from industrial_phm.application.file_feature_analysis import (
    FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID,
)
from industrial_phm.application.observation import SourceSnapshotEvidence
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.phase_unbalance import PHASE_UNBALANCE_CAPABILITY_ID


class OperationalAnalysisPresentationKind(StrEnum):
    """Known capability-specific evidence surfaces in Operations."""

    VIBRATION_FEATURES = "vibration-features"
    PHASE_UNBALANCE = "phase-unbalance"


_OPERATIONAL_ANALYSIS_PRESENTATION_KIND = {
    FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID: (
        OperationalAnalysisPresentationKind.VIBRATION_FEATURES
    ),
    PHASE_UNBALANCE_CAPABILITY_ID: OperationalAnalysisPresentationKind.PHASE_UNBALANCE,
}


def operational_analysis_presentation_kind(
    capability_id: str,
) -> OperationalAnalysisPresentationKind | None:
    """Resolve only explicitly supported capability renderers; unknown IDs stay unsupported."""
    if not isinstance(capability_id, str) or not capability_id.strip():
        raise ValueError("capability_id must not be empty")
    if capability_id != capability_id.strip():
        raise ValueError("capability_id must not contain surrounding whitespace")
    return _OPERATIONAL_ANALYSIS_PRESENTATION_KIND.get(capability_id)


def render_analysis_quality_markdown(run: AnalysisRun) -> str:
    """Render AnalysisRun input quality and recorded source snapshot provenance."""
    if not isinstance(run, AnalysisRun):
        raise ValueError("run must be an AnalysisRun")

    if run.data_quality.issues:
        issue_rows = "\n".join(
            (
                f"| {issue.severity.value} | {_format_code(issue.code)} | "
                f"{_escape_table_cell(issue.message)} |"
            )
            for issue in run.data_quality.issues
        )
        issues = "| Severity | Code | Evidence |\n| --- | --- | --- |\n" + issue_rows
    else:
        issues = "No recorded data-quality issue under this analysis input validation."

    return (
        "### Analysis input quality & provenance\n\n"
        f"Recorded data-quality state: **{run.data_quality.state.value.upper()}**. "
        "This state describes input validation evidence, not asset health.\n\n"
        f"{issues}\n\n"
        "| Provenance | Recorded value |\n"
        "| --- | --- |\n"
        f"| Source snapshots | {_format_snapshot_list(run.source_snapshots)} |"
    )


def _format_snapshot_list(values: Sequence[SourceSnapshotEvidence]) -> str:
    if not values:
        return "Not recorded"
    return ", ".join(
        f"{_format_code(value.name)} · {_format_code(value.sha256)}" for value in values
    )


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _format_code(value: str) -> str:
    fence = "`"
    while fence in value:
        fence += "`"
    return f"{fence}{value}{fence}"
