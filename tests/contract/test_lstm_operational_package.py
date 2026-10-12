"""Numeric LSTM packaging and causal, restart-safe inference over the shared PHM store."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("torch", reason="install the deep-learning extra")

from industrial_phm.application.phm_analysis import (
    PhmBinding,
    PreparedStep,
    SqlitePhmAnalysisStore,
    StepState,
    run_binding,
)
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_rul_lstm import get_xjtu_rul_lstm_configuration
from industrial_phm.models import fit_lstm_autoencoder, fit_lstm_rul_regression
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelPackageError,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    load_model_package,
    write_model_package,
)
from industrial_phm.sequences import (
    SequenceFeatureObservation,
    SequenceWindowSpec,
    construct_sequence_windows,
)

T0 = datetime(2026, 10, 12, tzinfo=UTC)
FEATURES = ("rms", "crest_factor")


def build_package(root: Path, kind: EstimatorKind):
    config = (
        get_xjtu_lstm_development_configuration()
        if kind is EstimatorKind.LSTM_AUTOENCODER
        else get_xjtu_rul_lstm_configuration()
    )
    parameters = {
        **config.model_parameters,
        "sequence_length": 3,
        "hidden_size": 4,
        "batch_size": 2,
        "epochs": 2,
    }
    config = replace(config, selected_features=FEATURES, model_parameters=parameters)
    rows = tuple((i / 10.0, (i + 1) / 10.0) for i in range(8))
    construction = construct_sequence_windows(
        tuple(
            SequenceFeatureObservation("run", "asset", "train", f"s{i}", i, row)
            for i, row in enumerate(rows)
        ),
        feature_set_id=config.feature_set_id,
        feature_names=FEATURES,
        spec=SequenceWindowSpec(length=3, stride=1),
    )
    if kind is EstimatorKind.LSTM_AUTOENCODER:
        model = fit_lstm_autoencoder(config, construction)
        output = PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="reconstruction",
            threshold=0.01,
            threshold_rule="test",
            review_interval=ReviewIntervalRule(2, 1),
            provides_feature_contributions=True,
        )
    else:
        model = fit_lstm_rul_regression(config, construction, (5.0, 4.0, 3.0, 2.0, 1.0, 0.0))
        output = PackageOutputSpec(
            task=ModelTask.RUL_ESTIMATE,
            value_name="rul",
            unit="acquisition-interval",
            endpoint_semantics="last-recorded-acquisition",
        )
    flat = [tuple(v for row in window.values for v in row) for window in construction.windows]
    manifest = write_model_package(
        root,
        PackageBuild(
            recipe_id="tiny-" + kind.value,
            estimator_kind=kind,
            input=PackageInputSpec(
                step_kind=StepKind.ACQUISITION_SNAPSHOT,
                channels=("h", "v"),
                feature_set_id=config.feature_set_id,
                feature_names=FEATURES,
                sequence_length=3,
            ),
            output=output,
            preprocessing=AffinePreprocessing((0.0, 0.0), (1.0, 1.0)),
            estimator_state={
                "input_size": 2,
                "model_parameters": dict(parameters),
                "weights": model.export_weights(),
            },
            fit_rows=None,
            probe_rows=flat[:2],
            training_scope={"dataset_id": "synthetic"},
            validation={},
            applicability={"operating_condition": ["c1"]},
            created_at=T0.isoformat(),
            code_revision="0" * 40,
        ),
    )
    return load_model_package(root / manifest.package_id), model, construction, rows, flat


@pytest.mark.parametrize("kind", [EstimatorKind.LSTM_AUTOENCODER, EstimatorKind.LSTM_RUL])
def test_same_fitted_weights_reload_and_batching_cannot_change_outputs(tmp_path, kind) -> None:
    package, model, construction, _rows, flat = build_package(tmp_path / "models", kind)
    batch = package.evaluate(flat)
    assert batch == tuple(package.evaluate([row])[0] for row in flat)
    reloaded = load_model_package(tmp_path / "models" / package.package_id)
    assert reloaded.evaluate(flat) == batch
    if kind is EstimatorKind.LSTM_RUL:
        assert batch == pytest.approx(model.predict(construction), abs=1e-5)
    else:
        from industrial_phm.models.reconstruction_scoring import score_reconstructions

        research = score_reconstructions(construction, model.reconstruct(construction))
        assert batch == pytest.approx(research.scores, abs=1e-7)
        contributions = package.feature_contributions(flat)
        assert contributions is not None
        assert [sum(row.values()) for row in contributions] == pytest.approx(batch, abs=1e-12)


def test_sequence_warmup_is_durable_and_future_inputs_cannot_change_prior_outputs(tmp_path) -> None:
    package, _model, _construction, rows, flat = build_package(
        tmp_path / "models", EstimatorKind.LSTM_RUL
    )

    def step(i, row):
        return PreparedStep(
            f"s{i}", i, True, {"ordinal": i}, features=row, context={"operating_condition": "c1"}
        )

    path = tmp_path / "phm.sqlite"
    store = SqlitePhmAnalysisStore(path)
    binding = PhmBinding(
        "b", package.package_id, "source", "asset", StepKind.ACQUISITION_SNAPSHOT, T0
    )
    store.create_binding(binding)
    prefix = run_binding(
        store,
        binding,
        package,
        [step(i + 1, row) for i, row in enumerate(rows[:2])],
        now=lambda: T0,
    )
    assert all(r.state is StepState.SKIPPED and "warm-up" in r.reason for r in prefix)
    # Fresh store and model objects, as after a process restart.
    store = SqlitePhmAnalysisStore(path)
    reloaded = load_model_package(tmp_path / "models" / package.package_id)
    suffix = run_binding(
        store,
        binding,
        reloaded,
        [step(i + 3, row) for i, row in enumerate(rows[2:])],
        now=lambda: T0,
    )
    assert [r.output["estimate"] for r in suffix] == list(package.evaluate(flat))
    assert suffix[0].output["sequence_positions"] == [1, 2, 3]
    assert run_binding(store, binding, reloaded, [step(8, rows[-1])], now=lambda: T0) == ()
    prior = [r.output for r in store.list_results("b")[:4]]
    run_binding(store, binding, reloaded, [step(9, (10000.0, 20000.0))], now=lambda: T0)
    assert [r.output for r in store.list_results("b")[:4]] == prior
    # A gap must rebuild the sequence rather than joining unrelated acquisitions.
    (gap,) = run_binding(store, binding, reloaded, [step(20, rows[0])], now=lambda: T0)
    assert gap.state is StepState.SKIPPED and "1/3" in gap.reason


def test_missing_deep_learning_runtime_is_explicit_and_does_not_fake_a_prediction(
    tmp_path, monkeypatch
) -> None:
    from industrial_phm.models import package_lstm

    package, *_ = build_package(tmp_path / "models", EstimatorKind.LSTM_RUL)
    original = package_lstm.import_module

    def missing(name):
        if name == "torch":
            raise ModuleNotFoundError("torch")
        return original(name)

    monkeypatch.setattr(package_lstm, "import_module", missing)
    with pytest.raises(ModelPackageError, match="deep-learning extra"):
        load_model_package(tmp_path / "models" / package.package_id)


def test_rul_runs_only_inside_every_declared_condition(tmp_path) -> None:
    package, *_ = build_package(tmp_path / "models", EstimatorKind.LSTM_RUL)
    package.manifest = replace(
        package.manifest,
        applicability={
            "dataset_id": ["xjtu-sy"],
            "operating_condition": ["35Hz12kN"],
            "recorded_replay": ["true"],
        },
    )
    store = SqlitePhmAnalysisStore(tmp_path / "scope.sqlite")
    binding = PhmBinding(
        "b", package.package_id, "source", "asset", StepKind.ACQUISITION_SNAPSHOT, T0
    )
    store.create_binding(binding)
    inside = {"dataset_id": "xjtu-sy", "operating_condition": "35Hz12kN", "recorded_replay": "true"}

    def step(position: int, **context: str) -> PreparedStep:
        return PreparedStep(
            f"s{position}", position, True, {}, features=(0.1, 0.2), context={**inside, **context}
        )

    other, live, unstated = run_binding(
        store,
        binding,
        package,
        [step(1, dataset_id="aihub-239"), step(2, recorded_replay="false"), step(3)],
        now=lambda: T0,
    )
    assert other.state is StepState.SKIPPED and other.output == {}
    assert (
        other.reason == "RUL applicability unavailable: dataset_id=aihub-239 is outside ['xjtu-sy']"
    )
    assert live.reason is not None and "recorded_replay=false" in live.reason
    # The third step is inside, but a rejected step broke the causal sequence: it warms up again.
    assert unstated.reason is not None and "sequence warm-up: 1/3" in unstated.reason
