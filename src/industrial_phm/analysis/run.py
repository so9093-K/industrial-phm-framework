"""Application use case that connects prepared sensor source to an AnalysisView."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from industrial_phm.adapters import XjtuSySourceError, validate_xjtu_source
from industrial_phm.analysis.view import (
    AnalysisView,
    AnalysisViewError,
    load_xjtu_lstm_analysis_view,
)
from industrial_phm.experiments.xjtu_lstm_result import run_xjtu_lstm_development_evaluation


class AnalysisRunError(RuntimeError):
    """Raised when a user-facing analysis execution cannot complete."""


def _resolve_current_git_revision() -> str:
    """Return HEAD for a clean tracked checkout used by a user-triggered analysis run."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tracked_status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise AnalysisRunError(
            "cannot determine the current Git revision; run the analysis from a Git checkout"
        ) from error

    if tracked_status:
        raise AnalysisRunError(
            "tracked Git files have local changes; commit or revert them before creating "
            "a versioned analysis result"
        )
    return head


@dataclass(frozen=True, slots=True)
class XjtuLstmAnalysisRunPlan:
    """Read-only preflight plan for one XJTU LSTM retrospective analysis run."""

    source: Path
    result_path: Path
    source_acquisition_count: int | None
    bearing_run_count: int | None
    checked_acquisition_count: int | None
    pipeline_stages: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready_to_run(self) -> bool:
        """Return whether the preflight plan has no known execution blocker."""
        return not self.blockers


_XJTU_LSTM_PIPELINE_STAGES = (
    "validate prepared XJTU-SY source profile",
    "extract vibration-statistical-v1 features",
    "fit train-only robust preprocessing state",
    "construct train/reference and validation sequences",
    "fit deterministic CPU LSTM autoencoder",
    "score validation reconstruction mismatch",
    "evaluate retrospective development evidence",
    "write and reload validated analysis artifact",
)


def plan_xjtu_lstm_analysis(
    source: Path,
    result_path: Path,
) -> XjtuLstmAnalysisRunPlan:
    """Validate run prerequisites without starting numerical model execution."""
    blockers: list[str] = []
    warnings: list[str] = []
    source_acquisition_count: int | None = None
    bearing_run_count: int | None = None
    checked_acquisition_count: int | None = None

    try:
        report = validate_xjtu_source(source)
    except (OSError, XjtuSySourceError) as error:
        blockers.append(str(error))
    else:
        source_acquisition_count = report.acquisition_count
        bearing_run_count = report.bearing_run_count
        checked_acquisition_count = report.checked_acquisition_count
        if not report.profile_matches:
            blockers.extend(
                f"source profile mismatch: {issue}" for issue in report.profile_issues
            )

    if result_path.exists():
        if result_path.is_dir():
            blockers.append(f"result path points to a directory: {result_path}")
        else:
            warnings.append(f"existing result file will be replaced: {result_path}")

    warnings.append(
        "actual execution requires a clean tracked Git checkout when code_revision is not supplied"
    )
    warnings.append(
        "this run produces retrospective development evidence, not live fault state or maintenance advice"
    )

    return XjtuLstmAnalysisRunPlan(
        source=source,
        result_path=result_path,
        source_acquisition_count=source_acquisition_count,
        bearing_run_count=bearing_run_count,
        checked_acquisition_count=checked_acquisition_count,
        pipeline_stages=_XJTU_LSTM_PIPELINE_STAGES,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


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
    code_revision: str | None = None,
) -> XjtuLstmAnalysisRun:
    """Run the existing frozen XJTU LSTM path and return its validated presentation view.

    This is an application orchestration boundary, not a new numerical pipeline. It preserves
    the retrospective development semantics of the underlying experiment and immediately
    validates the generated artifact through the same AnalysisView used by the user surface.
    """
    resolved_revision = _resolve_current_git_revision() if code_revision is None else code_revision

    try:
        run_xjtu_lstm_development_evaluation(
            source,
            result_path,
            code_revision=resolved_revision,
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
