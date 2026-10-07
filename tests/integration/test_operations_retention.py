import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    PHASE_UNBALANCE_CAPABILITY_ID,
    FindingReviewAction,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    SqliteObservationWindowRepository,
    SqlitePhaseUnbalanceRepository,
    SqliteWindowAnalysisLedger,
    WindowAnalysisCursor,
    WindowAnalysisOutcome,
    WindowAnalysisState,
    create_finding_review_event,
    create_human_review_finding,
)
from industrial_phm.application.phase_unbalance import (
    PHASE_UNBALANCE_ALGORITHM_VERSION,
    phase_unbalance_policy_digest,
    run_phase_unbalance_on_window,
)
from industrial_phm.cli import main
from industrial_phm.runtime.operations_retention import apply_operations_retention
from industrial_phm.runtime.operations_workspace import OperationsWorkspace
from tests.support.window_analysis import START, finalized_window

NOW = START + timedelta(days=10)  # retention cutoff START + 3 days
DIGEST = phase_unbalance_policy_digest()


def _cursor(window) -> WindowAnalysisCursor:
    return WindowAnalysisCursor(
        PHASE_UNBALANCE_CAPABILITY_ID,
        PHASE_UNBALANCE_ALGORITHM_VERSION,
        DIGEST,
        window.window_end,
        window.window_id,
    )


def _workspace(tmp_path: Path) -> OperationsWorkspace:
    workspace = OperationsWorkspace(tmp_path / "workspace")
    windows = {
        "w-old": finalized_window("w-old", START),
        "w-open": finalized_window("w-open", START + timedelta(hours=1)),
        "w-closed": finalized_window("w-closed", START + timedelta(hours=2)),
        "w-unanalyzed": finalized_window("w-unanalyzed", START + timedelta(days=1)),
        "w-recent": finalized_window("w-recent", START + timedelta(days=9)),
    }
    SqliteObservationWindowRepository(workspace.window_state_path).record_windows(
        tuple(windows.values())
    )
    ledger = SqliteWindowAnalysisLedger(workspace.analysis_ledger_path)
    ledger.record_skip_and_advance(
        WindowAnalysisOutcome(
            "w-old",
            PHASE_UNBALANCE_CAPABILITY_ID,
            PHASE_UNBALANCE_ALGORITHM_VERSION,
            DIGEST,
            WindowAnalysisState.SKIPPED,
            START,
            reason="missing phase",
        ),
        _cursor(windows["w-old"]),
    )
    results = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    findings = JsonOperationalFindingRepository(workspace.finding_state_path)
    reviews = JsonFindingReviewRepository(workspace.maintenance_review_state_path)
    for window_id in ("w-open", "w-closed"):
        result = results.record_window_result(run_phase_unbalance_on_window(windows[window_id]))
        finding = create_human_review_finding(result)
        findings.record(finding)
        ledger.advance_cursor(_cursor(windows[window_id]))
        if window_id == "w-closed":
            for action in (FindingReviewAction.ACKNOWLEDGE, FindingReviewAction.CLOSE):
                reviews.record(create_finding_review_event(finding, action=action))
    return workspace


def _stored(workspace: OperationsWorkspace) -> set[str]:
    repository = SqliteObservationWindowRepository(workspace.window_state_path)
    return {bounds[0] for bounds in repository.list_window_bounds()}


def test_retention_deletes_only_analyzed_unprotected_windows_older_than_cutoff(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)

    preview = apply_operations_retention(workspace, now=NOW, dry_run=True)
    assert preview.history is None
    assert preview.windows is not None
    assert preview.windows.deleted_window_count == 2
    assert preview.windows.protected_window_count == 1
    assert preview.windows.unanalyzed_window_count == 1
    assert len(_stored(workspace)) == 5

    result = apply_operations_retention(workspace, now=NOW)
    assert result.windows is not None
    assert result.windows.deleted_window_count == 2
    assert result.windows.deleted_skipped_outcome_count == 1
    assert result.protection.window_ids == frozenset({"w-open"})
    # Open-review evidence, a window analysis has not passed yet, and recent windows stay.
    assert _stored(workspace) == {"w-open", "w-unanalyzed", "w-recent"}
    assert SqliteWindowAnalysisLedger(workspace.analysis_ledger_path).list_skipped() == ()
    with sqlite3.connect(workspace.window_state_path) as connection:
        orphaned = connection.execute(
            "SELECT count(*) FROM delivery_identity WHERE window_id IN ('w-old', 'w-closed')"
        ).fetchone()
    assert orphaned == (0,)

    # A rerun has nothing left to delete.
    again = apply_operations_retention(workspace, now=NOW)
    assert again.windows is not None and again.windows.deleted_window_count == 0


def test_retention_keeps_windows_until_analysis_has_a_cursor(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "workspace")
    SqliteObservationWindowRepository(workspace.window_state_path).record_window(
        finalized_window("w-old", START)
    )
    result = apply_operations_retention(workspace, now=NOW)
    assert result.windows is not None
    assert result.windows.unanalyzed_window_count == 1
    assert _stored(workspace) == {"w-old"}


def test_retention_refuses_to_delete_when_an_open_review_result_is_missing(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    orphan = run_phase_unbalance_on_window(finalized_window("w-orphan", START))
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(orphan)
    )
    with pytest.raises(ValueError, match="refusing to delete"):
        apply_operations_retention(workspace, now=NOW)
    assert len(_stored(workspace)) == 5


def test_retain_command_reports_a_dry_run(tmp_path: Path, capsys) -> None:
    workspace = _workspace(tmp_path)
    assert main(["maintenance", "history", "retain", str(workspace.root), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "dry_run=yes" in output
    assert "protected_windows=1" in output
    assert len(_stored(workspace)) == 5
    assert main(["maintenance", "history", "retain", str(workspace.root), "--retention-days", "0"])
    assert "--retention-days must be at least 1" in capsys.readouterr().err
