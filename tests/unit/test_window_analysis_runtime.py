from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.live_window_analysis import (
    WindowAnalysisOutcome,
    WindowAnalysisState,
)
from industrial_phm.application.window_analysis_runtime import (
    JsonWindowAnalysisRuntimeRepository,
    WindowAnalysisRunnerState,
)

T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _outcome(
    window_id: str,
    state: WindowAnalysisState,
    *,
    at: datetime,
) -> WindowAnalysisOutcome:
    return WindowAnalysisOutcome(
        window_id=window_id,
        capability_id="three-phase-unbalance-v1",
        algorithm_version="phase-unbalance-max-deviation-v2",
        analysis_policy_digest="a" * 64,
        state=state,
        recorded_at=at,
        analysis_run_id=(f"run-{window_id}" if state == WindowAnalysisState.ANALYZED else None),
        reason=("missing phase T" if state == WindowAnalysisState.SKIPPED else None),
    )


def test_runtime_repository_tracks_runner_cycles_across_restart(tmp_path) -> None:
    repository = JsonWindowAnalysisRuntimeRepository(tmp_path / "analysis-runtime.json")

    started = repository.record_start(T0)
    assert started.state == WindowAnalysisRunnerState.RUNNING
    assert started.cycle_count == 0

    first = repository.record_cycle(
        (
            _outcome("w-1", WindowAnalysisState.ANALYZED, at=T0 + timedelta(seconds=2)),
            _outcome("w-2", WindowAnalysisState.SKIPPED, at=T0 + timedelta(seconds=3)),
        ),
        completed_at=T0 + timedelta(seconds=4),
    )
    assert first.cycle_count == 1
    assert first.analyzed_count == 1
    assert first.skipped_count == 1
    assert first.last_analysis_run_id == "run-w-1"
    assert first.last_skip_reason == "missing phase T"

    stopped = repository.record_stop(T0 + timedelta(seconds=5))
    assert stopped.state == WindowAnalysisRunnerState.STOPPED

    restarted = repository.record_start(T0 + timedelta(minutes=1))
    assert restarted.state == WindowAnalysisRunnerState.RUNNING
    assert restarted.started_at == T0 + timedelta(minutes=1)
    assert restarted.analyzed_count == 1
    assert restarted.skipped_count == 1
    assert restarted.last_analysis_run_id == "run-w-1"


def test_runtime_repository_records_failure_without_discarding_last_success(tmp_path) -> None:
    repository = JsonWindowAnalysisRuntimeRepository(tmp_path / "analysis-runtime.json")
    repository.record_start(T0)
    repository.record_cycle(
        (_outcome("w-1", WindowAnalysisState.ANALYZED, at=T0 + timedelta(seconds=1)),),
        completed_at=T0 + timedelta(seconds=2),
    )

    failed = repository.record_failure(
        "analysis repository unreadable",
        occurred_at=T0 + timedelta(seconds=3),
    )

    assert failed.state == WindowAnalysisRunnerState.FAILED
    assert failed.last_failure == "analysis repository unreadable"
    assert failed.last_analysis_run_id == "run-w-1"
    assert repository.load() == failed


def test_runtime_repository_rejects_unknown_schema(tmp_path) -> None:
    path = tmp_path / "analysis-runtime.json"
    path.write_text('{"schema":"future"}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported window analysis runtime schema"):
        JsonWindowAnalysisRuntimeRepository(path).load()
