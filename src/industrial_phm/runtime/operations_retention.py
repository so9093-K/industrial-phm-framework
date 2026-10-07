"""Apply the live-evidence retention policy to one Operations workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from industrial_phm.application import (
    JsonFileFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    OperationalAnalysisResult,
    SqliteObservationWindowRepository,
    SqlitePhaseUnbalanceRepository,
    SqliteWindowAnalysisLedger,
)
from industrial_phm.application.history_retention import (
    DEFAULT_LIVE_RETENTION,
    RetentionProtection,
    open_review_protection,
    retention_cutoff,
)
from industrial_phm.history import (
    DuckLakeAssetHistory,
    DuckLakeAssetHistoryConfig,
    DuckLakeRetentionResult,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


@dataclass(frozen=True, slots=True)
class WindowRetentionResult:
    """Finalized windows deleted, or kept because they are protected or not analyzed yet."""

    deleted_window_count: int
    deleted_skipped_outcome_count: int
    protected_window_count: int
    unanalyzed_window_count: int


@dataclass(frozen=True, slots=True)
class OperationsRetentionResult:
    cutoff: datetime
    dry_run: bool
    protection: RetentionProtection
    windows: WindowRetentionResult | None
    history: DuckLakeRetentionResult | None


def apply_operations_retention(
    workspace: OperationsWorkspace,
    *,
    now: datetime,
    retention: timedelta = DEFAULT_LIVE_RETENTION,
    dry_run: bool = False,
) -> OperationsRetentionResult:
    """Delete live evidence older than the retention period, except open-review evidence.

    The protection set is computed first and any failure to read review or result
    state aborts before anything is deleted. Windows are deleted only after every
    recorded analysis policy has passed them, and their skipped outcomes before them.
    """
    if not workspace.root.is_dir():
        raise ValueError(f"Operations workspace does not exist: {workspace.root}")
    cutoff = retention_cutoff(now, retention)
    protection = _open_review_protection(workspace)
    windows = _apply_window_retention(workspace, cutoff, protection, dry_run=dry_run)
    history = None
    if workspace.history_catalog_path.is_file():
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
        ).apply_live_retention(cutoff=cutoff, protection=protection, dry_run=dry_run)
    return OperationsRetentionResult(cutoff, dry_run, protection, windows, history)


def _open_review_protection(workspace: OperationsWorkspace) -> RetentionProtection:
    findings = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
    review_events = JsonFindingReviewRepository(
        workspace.maintenance_review_state_path
    ).list_events()
    reviewed_run_ids = {finding.analysis_run_id for finding in findings}
    results: list[OperationalAnalysisResult] = list(
        JsonFileFeatureAnalysisRepository(workspace.file_feature_analysis_path).list_results()
    )
    if reviewed_run_ids:
        results.extend(
            SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).find_results(
                reviewed_run_ids
            )
        )
    return open_review_protection(
        analysis_results=results, findings=findings, review_events=review_events
    )


def _apply_window_retention(
    workspace: OperationsWorkspace,
    cutoff: datetime,
    protection: RetentionProtection,
    *,
    dry_run: bool,
) -> WindowRetentionResult | None:
    if not workspace.window_state_path.is_file():
        return None
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    ledger = SqliteWindowAnalysisLedger(workspace.analysis_ledger_path)
    analyzed_through = (
        ledger.analyzed_through() if workspace.analysis_ledger_path.is_file() else None
    )
    eligible: list[str] = []
    protected = unanalyzed = 0
    for window_id, source_id, start_at, end_at in windows.list_window_bounds():
        if end_at >= cutoff:
            continue
        if window_id in protection.window_ids or protection.covers(source_id, start_at, end_at):
            protected += 1
        elif analyzed_through is None or (end_at, window_id) > analyzed_through:
            unanalyzed += 1
        else:
            eligible.append(window_id)
    skipped_deleted = deleted = 0
    if not dry_run and eligible:
        # Skipped outcomes first: an interruption then leaves only analyzed windows.
        skipped_deleted = ledger.delete_skipped(eligible)
        deleted = windows.delete_windows(eligible)
    return WindowRetentionResult(
        deleted_window_count=len(eligible) if dry_run else deleted,
        deleted_skipped_outcome_count=skipped_deleted,
        protected_window_count=protected,
        unanalyzed_window_count=unanalyzed,
    )
