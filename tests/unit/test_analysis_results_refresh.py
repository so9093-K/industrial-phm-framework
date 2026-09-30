import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from industrial_phm.application import JsonPhaseUnbalanceRepository
from industrial_phm.presentation.analysis_results import (
    load_analysis_results,
    reload_analysis_results,
    retained_option,
)

T0 = datetime(2026, 9, 30, 9, tzinfo=UTC)


def _result(run_id):
    return SimpleNamespace(run=SimpleNamespace(analysis_run_id=run_id))


def test_refresh_reads_results_written_by_another_process():
    stored = [(_result("run-1"),)]
    first = load_analysis_results(lambda: stored[-1], now=T0)
    # Results present at startup are existing results, not newly added ones.
    assert (len(first.results), first.loaded_at, first.error, first.added) == (1, T0, "", 0)

    stored.append((_result("run-1"), _result("run-2")))
    later = T0 + timedelta(minutes=1)
    refreshed = reload_analysis_results(lambda: stored[-1], first, now=later)
    assert [r.run.analysis_run_id for r in refreshed.results] == ["run-1", "run-2"]
    assert (refreshed.loaded_at, refreshed.error, refreshed.added) == (later, "", 1)

    unchanged = reload_analysis_results(lambda: stored[-1], refreshed, now=later)
    assert unchanged.added == 0


def test_failed_refresh_keeps_last_successful_results_and_reports_the_failure(tmp_path):
    path = tmp_path / "phase-unbalance.json"
    repository = JsonPhaseUnbalanceRepository(path)
    previous = reload_analysis_results(
        lambda: (_result("run-1"),),
        load_analysis_results(repository.list_results, now=T0),
        now=T0,
    )

    path.write_text(json.dumps({"schema": "unknown"}))
    failed = reload_analysis_results(
        repository.list_results, previous, now=T0 + timedelta(minutes=1)
    )
    assert failed.results == previous.results
    assert failed.loaded_at == T0  # still the time of the last successful read
    assert failed.error.startswith("PhaseUnbalanceHistoryFormatError: ")
    assert failed.added == 0


def test_missing_repository_is_an_empty_successful_read(tmp_path):
    repository = JsonPhaseUnbalanceRepository(tmp_path / "absent.json")
    assert load_analysis_results(repository.list_results, now=T0).results == ()


def test_selection_survives_refresh_until_its_run_disappears():
    options = {"newest": "run-2", "older": "run-1"}
    assert retained_option(options, "run-1") == "older"
    assert retained_option({"newer": "run-3", **options}, "run-1") == "older"
    assert retained_option(options, "run-9") == "newest"
    assert retained_option(options, None) == "newest"
    assert retained_option({}, "run-1") is None


def test_chosen_asset_survives_a_refresh_that_adds_a_run():
    before = ("asset-A", "asset-B")
    assert retained_option({a: a for a in before}, "asset-B") == "asset-B"
    # A refreshed run for a new asset sorts before the chosen one.
    after = ("asset-0", "asset-A", "asset-B")
    assert retained_option({a: a for a in after}, "asset-B") == "asset-B"
    assert retained_option({a: a for a in ("asset-A",)}, "asset-B") == "asset-A"
