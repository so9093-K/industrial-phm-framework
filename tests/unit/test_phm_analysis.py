from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
    file_sha256,
    read_snapshot_waveform,
)
from industrial_phm.application.phm_analysis import (
    PhmBinding,
    PreparedStep,
    SqlitePhmAnalysisStore,
    StepState,
    advance_review_interval,
    run_binding,
)
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_CHANNELS,
    ELECTRICAL_WINDOW_FEATURE_NAMES,
    ELECTRICAL_WINDOW_FEATURE_SET_ID,
)
from industrial_phm.application.observation_window import DurableObservationWindow
from industrial_phm.application.phm_runner import (
    PackageCache,
    prepare_window_step,
    run_snapshot_bindings,
)
from industrial_phm.features.vibration import vibration_feature_names
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    LoadedModelPackage,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    load_model_package,
    write_model_package,
)

T0 = datetime(2026, 10, 12, tzinfo=UTC)
CHANNELS = ("h", "v")


def _clock() -> datetime:
    return T0


def _anomaly_package(
    tmp_path: Path, *, feature_names: tuple[str, ...] = ("x",)
) -> LoadedModelPackage:
    width = len(feature_names)
    manifest = write_model_package(
        tmp_path / "models",
        PackageBuild(
            recipe_id="identity-score-v1",
            estimator_kind=EstimatorKind.LINEAR,
            input=PackageInputSpec(
                step_kind=StepKind.ACQUISITION_SNAPSHOT,
                channels=CHANNELS,
                feature_set_id="vibration-statistical-v1",
                feature_names=feature_names,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="score",
                threshold=1.0,
                threshold_rule="fixed",
                review_interval=ReviewIntervalRule(min_consecutive_steps=2, max_gap_steps=1),
            ),
            preprocessing=AffinePreprocessing((0.0,) * width, (1.0,) * width),
            estimator_state={"coefficients": [1.0] + [0.0] * (width - 1), "intercept": 0.0},
            fit_rows=None,
            probe_rows=[[0.5] * width],
            training_scope={},
            validation={},
            applicability={},
            created_at=T0.isoformat(),
            code_revision="0" * 40,
        ),
    )
    return load_model_package(tmp_path / "models" / manifest.package_id)


def _rul_package(tmp_path: Path) -> LoadedModelPackage:
    manifest = write_model_package(
        tmp_path / "models",
        PackageBuild(
            recipe_id="identity-rul-v1",
            estimator_kind=EstimatorKind.LINEAR,
            input=PackageInputSpec(
                step_kind=StepKind.ACQUISITION_SNAPSHOT,
                channels=CHANNELS,
                feature_set_id="vibration-statistical-v1",
                feature_names=("x",),
            ),
            output=PackageOutputSpec(
                task=ModelTask.RUL_ESTIMATE,
                value_name="rul",
                unit="acquisition-interval",
                endpoint_semantics="last-recorded-acquisition",
            ),
            preprocessing=AffinePreprocessing((0.0,), (1.0,)),
            estimator_state={"coefficients": [1.0], "intercept": 0.0},
            fit_rows=None,
            probe_rows=[[3.0]],
            training_scope={},
            validation={},
            applicability={"operating_condition": ["c1"]},
            created_at=T0.isoformat(),
            code_revision="0" * 40,
        ),
    )
    return load_model_package(tmp_path / "models" / manifest.package_id)


def _bind(
    store: SqlitePhmAnalysisStore, package: LoadedModelPackage, binding_id: str = "b1"
) -> PhmBinding:
    binding = PhmBinding(
        binding_id, package.package_id, "src", "A", StepKind.ACQUISITION_SNAPSHOT, T0
    )
    store.create_binding(binding)
    return binding


def _step(
    position: int, value: float | None, *, context: dict[str, str] | None = None
) -> PreparedStep:
    return PreparedStep(
        step_key=f"s{position}",
        position=position,
        replay=True,
        input_reference={"ordinal": position},
        features=None if value is None else (value,),
        skip_reason="unreadable" if value is None else None,
        context=context or {},
    )


def test_each_step_is_recorded_exactly_once_across_store_instances(tmp_path: Path) -> None:
    package = _anomaly_package(tmp_path)
    path = tmp_path / "phm.sqlite"
    binding = _bind(SqlitePhmAnalysisStore(path), package)
    first = run_binding(
        SqlitePhmAnalysisStore(path), binding, package, [_step(1, 0.1), _step(2, 0.2)], now=_clock
    )
    again = run_binding(
        SqlitePhmAnalysisStore(path),
        binding,
        package,
        [_step(1, 0.1), _step(2, 0.2), _step(3, 0.3)],
        now=_clock,
    )
    assert [r.position for r in first] == [1, 2]
    assert [r.position for r in again] == [3]
    stored = SqlitePhmAnalysisStore(path).list_results("b1")
    assert [r.position for r in stored] == [1, 2, 3]
    assert len({r.analysis_run_id for r in stored}) == 3


def test_late_step_is_recorded_as_skip_without_touching_state(tmp_path: Path) -> None:
    package = _anomaly_package(tmp_path)
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    binding = _bind(store, package)
    run_binding(store, binding, package, [_step(1, 2.0), _step(3, 2.0)], now=_clock)
    before = store.progress("b1")
    (late,) = run_binding(store, binding, package, [_step(2, 5.0)], now=_clock)
    assert (
        late.state is StepState.SKIPPED and late.reason is not None and "late-step" in late.reason
    )
    after = store.progress("b1")
    assert after.cursor_position == 3 and after.state == before.state


def test_review_interval_opens_after_consecutive_crossings_and_survives_restart(
    tmp_path: Path,
) -> None:
    package = _anomaly_package(tmp_path)
    path = tmp_path / "phm.sqlite"
    binding = _bind(SqlitePhmAnalysisStore(path), package)
    run_binding(
        SqlitePhmAnalysisStore(path), binding, package, [_step(1, 0.5), _step(2, 1.5)], now=_clock
    )
    assert SqlitePhmAnalysisStore(path).list_intervals("b1") == ()
    # restart: the pending single crossing is part of committed state
    run_binding(SqlitePhmAnalysisStore(path), binding, package, [_step(3, 2.5)], now=_clock)
    (interval,) = SqlitePhmAnalysisStore(path).list_intervals("b1")
    assert (interval.start_position, interval.end_position, interval.open) == (2, 3, True)
    assert interval.peak_score == 2.5 and interval.step_count == 2
    # one quiet step is tolerated, the crossing after it extends the same interval
    run_binding(
        SqlitePhmAnalysisStore(path), binding, package, [_step(4, 0.1), _step(5, 1.2)], now=_clock
    )
    (interval,) = SqlitePhmAnalysisStore(path).list_intervals("b1")
    assert (interval.end_position, interval.step_count, interval.open) == (5, 3, True)
    # two quiet steps close it without widening the end
    run_binding(
        SqlitePhmAnalysisStore(path), binding, package, [_step(6, 0.1), _step(7, 0.1)], now=_clock
    )
    (interval,) = SqlitePhmAnalysisStore(path).list_intervals("b1")
    assert (interval.end_position, interval.open) == (5, False)


def test_single_crossing_does_not_open_an_interval() -> None:
    tracker, writes = advance_review_interval(
        {}, _step(1, 2.0), score=2.0, exceeds=True, min_consecutive_steps=2, max_gap_steps=1
    )
    assert writes == () and len(tracker["run"]) == 1
    tracker, writes = advance_review_interval(
        tracker, _step(2, 0.0), score=0.0, exceeds=False, min_consecutive_steps=2, max_gap_steps=1
    )
    assert writes == () and tracker == {}


def test_skipped_step_keeps_interval_state_and_records_reason(tmp_path: Path) -> None:
    package = _anomaly_package(tmp_path)
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    binding = _bind(store, package)
    run_binding(store, binding, package, [_step(1, 2.0)], now=_clock)
    state = store.progress("b1").state
    (skipped,) = run_binding(store, binding, package, [_step(2, None)], now=_clock)
    assert skipped.state is StepState.SKIPPED and skipped.reason == "unreadable"
    assert store.progress("b1").state == state


def test_rul_output_reports_change_and_applicability(tmp_path: Path) -> None:
    package = _rul_package(tmp_path)
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    binding = _bind(store, package)
    results = run_binding(
        store,
        binding,
        package,
        [
            _step(1, 100.0, context={"operating_condition": "c1"}),
            _step(2, 90.0, context={"operating_condition": "c2"}),
        ],
        now=_clock,
    )
    assert results[0].output["change_from_previous"] is None
    assert results[1].output["change_from_previous"] == -10.0
    assert [r.output["applicability"] for r in results] == ["inside", "outside"]
    assert results[0].output["unit"] == "acquisition-interval"


def test_change_feed_returns_only_newer_results(tmp_path: Path) -> None:
    package = _anomaly_package(tmp_path)
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    binding = _bind(store, package)
    run_binding(store, binding, package, [_step(1, 0.1)], now=_clock)
    seq = store.latest_change_seq()
    run_binding(store, binding, package, [_step(2, 0.2)], now=_clock)
    assert [r.position for r in store.list_results("b1", after_change_seq=seq)] == [2]


# Snapshots and runner --------------------------------------------------------

@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"channels": ("different channel meaning",)}, "channels differ"),
        ({"sampling_rate_hz": 10.0}, "fixed sampling rate"),
        ({"samples_per_step": 50}, "fixed sampling rate"),
    ],
)
def test_window_package_input_mismatch_is_skipped_with_a_reason(
    override: dict[str, object], reason: str
) -> None:
    window = DurableObservationWindow(
        window_id="w1",
        source_id="src",
        asset_id="A",
        window_start=T0,
        window_end=T0 + timedelta(minutes=5),
        watermark_at_close=T0 + timedelta(minutes=5),
        finalized_at=T0 + timedelta(minutes=6),
        expected_channel_ids=("raw-channel",),
        events=(),
    )
    spec = PackageInputSpec(
        step_kind=StepKind.OBSERVATION_WINDOW,
        channels=ELECTRICAL_WINDOW_CHANNELS,
        feature_set_id=ELECTRICAL_WINDOW_FEATURE_SET_ID,
        feature_names=ELECTRICAL_WINDOW_FEATURE_NAMES,
    )
    rejected = prepare_window_step(window, replace(spec, **override), recorded_replay=True)
    assert rejected.features is None
    assert reason in (rejected.skip_reason or "")
    assert rejected.input_reference["window_id"] == "w1"

    # The same feature set with its declared schema is still accepted for extraction.
    # This empty window is skipped for missing observations, not for schema mismatch.
    supported = prepare_window_step(window, spec, recorded_replay=True)
    assert supported.features is None
    assert "confirmed channel meaning missing" in (supported.skip_reason or "")



def _write_waveform(path: Path, scale: float) -> Path:
    rows = [f"{scale * ((i % 7) - 3):.6f},{scale * ((i % 5) - 2) + 0.1:.6f}" for i in range(64)]
    path.write_text("h,v\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _snapshot(
    path: Path, ordinal: int, *, channels: tuple[str, ...] = CHANNELS
) -> AcquisitionSnapshot:
    return AcquisitionSnapshot(
        source_id="src",
        asset_id="A",
        ordinal=ordinal,
        file_path=path.resolve(),
        sha256=file_sha256(path),
        channels=channels,
        sampling_rate_hz=1000.0,
        sample_count=64,
        delivered_at=T0 + timedelta(seconds=ordinal),
        replay=True,
        acquisition_period_seconds=60.0,
        metadata={"operating_condition": "c1"},
    )


def test_snapshot_repository_is_append_only_per_ordinal(tmp_path: Path) -> None:
    repo = SqliteAcquisitionSnapshotRepository(tmp_path / "snap.sqlite")
    a = _snapshot(_write_waveform(tmp_path / "1.csv", 1.0), 1)
    assert repo.record(a) is True
    assert repo.record(a) is False
    b = _snapshot(_write_waveform(tmp_path / "1b.csv", 2.0), 1)
    with pytest.raises(AcquisitionSnapshotError, match="different snapshot"):
        repo.record(b)
    assert [s.ordinal for s in repo.list_after("src", "A", after_ordinal=None)] == [1]


def test_snapshot_read_refuses_changed_file(tmp_path: Path) -> None:
    path = _write_waveform(tmp_path / "1.csv", 1.0)
    snapshot = _snapshot(path, 1)
    assert read_snapshot_waveform(snapshot).values[0] == (-3.0, -1.9)
    _write_waveform(path, 1.5)
    with pytest.raises(AcquisitionSnapshotError, match="SHA-256"):
        read_snapshot_waveform(snapshot)


def test_runner_processes_new_snapshots_and_skips_incompatible_ones(tmp_path: Path) -> None:
    names = vibration_feature_names(CHANNELS)
    package = _anomaly_package(tmp_path, feature_names=names)
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    _bind(store, package)
    repo = SqliteAcquisitionSnapshotRepository(tmp_path / "snap.sqlite")
    repo.record(_snapshot(_write_waveform(tmp_path / "1.csv", 1.0), 1))
    other = tmp_path / "2.csv"
    other.write_text("x,y\n" + "\n".join("1,2" for _ in range(64)) + "\n")
    repo.record(_snapshot(other, 2, channels=("x", "y")))
    cache = PackageCache(tmp_path / "models")
    (cycle,) = run_snapshot_bindings(store, repo, cache, now=_clock)
    assert [r.state for r in cycle.results] == [StepState.ANALYZED, StepState.SKIPPED]
    assert cycle.results[1].reason is not None and "channels differ" in cycle.results[1].reason
    repo.record(_snapshot(_write_waveform(tmp_path / "3.csv", 3.0), 3))
    (cycle,) = run_snapshot_bindings(store, repo, cache, now=_clock)
    assert [r.position for r in cycle.results] == [3]
    assert store.progress("b1").health == "ok"


def test_unloadable_package_marks_only_its_binding_unavailable(tmp_path: Path) -> None:
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    store.create_binding(
        PhmBinding("missing", "nope-000000000000", "src", "A", StepKind.ACQUISITION_SNAPSHOT, T0)
    )
    repo = SqliteAcquisitionSnapshotRepository(tmp_path / "snap.sqlite")
    (cycle,) = run_snapshot_bindings(store, repo, PackageCache(tmp_path / "models"), now=_clock)
    assert cycle.error is not None
    progress = store.progress("missing")
    assert progress.health == "unavailable" and progress.health_reason


def test_change_pages_preserve_late_steps_and_never_jump_past_unread_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from industrial_phm.application import phm_read

    package = _anomaly_package(tmp_path)
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    binding = _bind(store, package)
    run_binding(store, binding, package, [_step(i, 0.5) for i in (1, 3, 2, 4, 5)], now=_clock)
    monkeypatch.setattr(phm_read, "_SERIES_PAGE_SIZE", 2)
    snapshots = SqliteAcquisitionSnapshotRepository(tmp_path / "snapshots.sqlite")
    seen = []
    cursor = 0
    while True:
        page = phm_read.project_phm_series(
            store,
            tmp_path / "models",
            snapshots,
            binding_id=binding.binding_id,
            since_change_seq=cursor,
        )
        seen.extend(step["position"] for step in page["steps"])
        assert page["change_seq"] > cursor
        cursor = page["change_seq"]
        if not page["has_more"]:
            break
    assert seen == [1, 3, 2, 4, 5]
    assert store.list_results(binding.binding_id, after_change_seq=cursor) == ()


def test_missing_steps_cannot_turn_separated_crossings_into_a_consecutive_run(
    tmp_path: Path,
) -> None:
    package = _anomaly_package(tmp_path)
    store = SqlitePhmAnalysisStore(tmp_path / "gap.sqlite")
    binding = _bind(store, package)
    run_binding(store, binding, package, [_step(1, 2.0), _step(5, 2.0)], now=_clock)
    assert store.list_intervals("b1") == ()
    run_binding(store, binding, package, [_step(6, 2.0)], now=_clock)
    assert store.list_intervals("b1")[0].start_position == 5
