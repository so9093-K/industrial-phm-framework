from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_FEATURE_NAMES,
    ELECTRICAL_WINDOW_FEATURE_SET_ID,
)
from industrial_phm.application.observation_window import DurableObservationWindow
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_runner import (
    PackageCache,
    run_window_bindings,
    window_position,
)
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    write_model_package,
)
from tests.support.window_analysis import START, finalized_window

WIDTH = len(ELECTRICAL_WINDOW_FEATURE_NAMES)


class _Windows:
    def __init__(self, windows: list[DurableObservationWindow]) -> None:
        self._windows = sorted(windows, key=lambda w: (w.window_end, w.window_id))

    def list_windows_after(
        self,
        *,
        after_window_end: datetime | None = None,
        after_window_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[DurableObservationWindow, ...]:
        key = (after_window_end, after_window_id or "")
        return tuple(
            w
            for w in self._windows
            if after_window_end is None or (w.window_end, w.window_id) > key
        )[:limit]


def _package(models: Path) -> str:
    return write_model_package(
        models,
        PackageBuild(
            recipe_id="window-pca-v1",
            estimator_kind=EstimatorKind.PCA_RESIDUAL,
            input=PackageInputSpec(
                step_kind=StepKind.OBSERVATION_WINDOW,
                channels=("phase current R/S/T [A]", "phase voltage R/S/T [V]", "frequency [Hz]"),
                feature_set_id=ELECTRICAL_WINDOW_FEATURE_SET_ID,
                feature_names=ELECTRICAL_WINDOW_FEATURE_NAMES,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="spe",
                threshold=1.0,
                threshold_rule="fixed-for-test",
                review_interval=ReviewIntervalRule(2, 1),
                provides_feature_contributions=True,
            ),
            preprocessing=AffinePreprocessing((0.0,) * WIDTH, (1.0,) * WIDTH),
            estimator_state={"mean": [0.0] * WIDTH, "components": [[1.0] + [0.0] * (WIDTH - 1)]},
            fit_rows=None,
            probe_rows=[[1.0] * WIDTH],
            training_scope={},
            validation={},
            applicability={},
            created_at=START.isoformat(),
            code_revision="0" * 40,
        ),
    ).package_id


def test_window_binding_records_each_window_once_with_reason_and_declared_replay(
    tmp_path: Path,
) -> None:
    package_id = _package(tmp_path / "models")
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    store.create_binding(
        PhmBinding(
            "w1",
            package_id,
            "site-opcua",
            "motor-7",
            StepKind.OBSERVATION_WINDOW,
            START,
            recorded_replay=True,
        )
    )
    windows = [
        finalized_window("a", START),
        finalized_window("b", START + timedelta(minutes=1)),
    ]
    cache = PackageCache(tmp_path / "models")
    (cycle,) = run_window_bindings(store, _Windows(windows), cache, now=lambda: START)
    assert [r.position for r in cycle.results] == [window_position(w) for w in windows]
    first = cycle.results[0]
    # The fixture binds voltages only: no current or frequency meaning, so nothing is scored.
    assert first.state is StepState.SKIPPED
    assert first.reason is not None and "confirmed channel meaning missing" in first.reason
    assert first.replay and first.input_reference["window_id"] == "a"
    assert first.event_start == START
    (again,) = run_window_bindings(store, _Windows(windows), cache, now=lambda: START)
    assert again.results == ()
    later = [*windows, finalized_window("c", START + timedelta(minutes=2))]
    (third,) = run_window_bindings(store, _Windows(later), cache, now=lambda: datetime.now(UTC))
    assert [r.input_reference["window_id"] for r in third.results] == ["c"]
