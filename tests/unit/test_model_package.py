from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

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
    is_retired_package,
    load_model_package,
    write_model_package,
)

FEATURES = ("f.a", "f.b", "f.c")


def _input() -> PackageInputSpec:
    return PackageInputSpec(
        step_kind=StepKind.ACQUISITION_SNAPSHOT,
        channels=("ch1",),
        feature_set_id="test-features-v1",
        feature_names=FEATURES,
        sampling_rate_hz=100.0,
        samples_per_step=8,
    )


def _linear_build(**overrides: object) -> PackageBuild:
    values: dict[str, object] = {
        "recipe_id": "test-linear-v1",
        "estimator_kind": EstimatorKind.LINEAR,
        "input": _input(),
        "output": PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="linear_score",
            threshold=1.0,
            threshold_rule="fixed-for-test",
            review_interval=ReviewIntervalRule(2, 1),
        ),
        "preprocessing": AffinePreprocessing(center=(1.0, 2.0, 3.0), scale=(2.0, 4.0, 8.0)),
        "estimator_state": {"coefficients": [0.5, -1.25, 3.0], "intercept": 10.0},
        "fit_rows": None,
        "probe_rows": [[1.0, 2.0, 3.0], [3.0, 6.0, 11.0]],
        "training_scope": {"dataset_id": "test", "asset_ids": ["A"]},
        "validation": {"note": "none"},
        "applicability": {"operating_condition": ["c1"]},
        "created_at": "2026-10-12T00:00:00+00:00",
        "code_revision": "0" * 40,
    }
    values.update(overrides)
    return PackageBuild(**values)  # type: ignore[arg-type]


def _iforest_build(rows: np.ndarray) -> PackageBuild:
    return PackageBuild(
        recipe_id="test-iforest-v1",
        estimator_kind=EstimatorKind.ISOLATION_FOREST_REFIT,
        input=_input(),
        output=PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="isolation_forest_score",
            threshold=0.55,
            threshold_rule="fixed-for-test",
            review_interval=ReviewIntervalRule(2, 1),
        ),
        preprocessing=AffinePreprocessing(center=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)),
        estimator_state={
            "n_estimators": 64,
            "max_samples": "auto",
            "contamination": "auto",
            "max_features": 1.0,
            "bootstrap": False,
            "random_seed": 42,
        },
        fit_rows=rows.tolist(),
        probe_rows=rows[:5].tolist(),
        training_scope={"dataset_id": "test"},
        validation={},
        applicability={},
        created_at="2026-10-12T00:00:00+00:00",
        code_revision="0" * 40,
    )


def test_linear_package_round_trip_matches_affine_then_linear(tmp_path: Path) -> None:
    manifest = write_model_package(tmp_path, _linear_build())
    assert manifest.package_id.startswith("test-linear-v1-")
    package = load_model_package(tmp_path / manifest.package_id)
    (value,) = package.evaluate([[3.0, 6.0, 11.0]])
    assert value == pytest.approx(10.0 + 0.5 * 1.0 - 1.25 * 1.0 + 3.0 * 1.0)
    assert package.manifest.output.threshold == 1.0
    assert dict(package.manifest.applicability) == {"operating_condition": ("c1",)}


def test_package_id_is_content_derived_and_rewrite_is_idempotent(tmp_path: Path) -> None:
    first = write_model_package(tmp_path, _linear_build())
    again = write_model_package(tmp_path, _linear_build())
    changed = {"coefficients": [0.5, -1.25, 3.0], "intercept": 11.0}
    other = write_model_package(tmp_path, _linear_build(estimator_state=changed))
    assert first.package_id == again.package_id
    assert other.package_id != first.package_id


def test_isolation_forest_refit_matches_direct_fit(tmp_path: Path) -> None:
    rows = np.random.default_rng(7).normal(size=(200, 3))
    manifest = write_model_package(tmp_path, _iforest_build(rows))
    package = load_model_package(tmp_path / manifest.package_id)
    direct = IsolationForest(n_estimators=64, n_jobs=1, random_state=42, max_features=1.0).fit(rows)
    probe = rows[10:20]
    assert package.evaluate(probe.tolist()) == tuple(-direct.score_samples(probe))


def test_tampered_payload_is_refused(tmp_path: Path) -> None:
    manifest = write_model_package(tmp_path, _linear_build())
    state_path = tmp_path / manifest.package_id / "state.json"
    state = json.loads(state_path.read_text())
    state["estimator"]["intercept"] = 99.0
    state_path.write_text(json.dumps(state))
    with pytest.raises(ModelPackageError, match="digest mismatch"):
        load_model_package(tmp_path / manifest.package_id)


def test_tampered_manifest_is_refused(tmp_path: Path) -> None:
    manifest = write_model_package(tmp_path, _linear_build())
    path = tmp_path / manifest.package_id / "package.json"
    body = json.loads(path.read_text())
    body["output"]["value_name"] = "renamed"
    path.write_text(json.dumps(body))
    with pytest.raises(ModelPackageError, match="does not match"):
        load_model_package(tmp_path / manifest.package_id)


def test_probe_mismatch_is_refused_even_with_consistent_digests(tmp_path: Path) -> None:
    manifest = write_model_package(tmp_path, _linear_build())
    root = tmp_path / manifest.package_id
    state_path = root / "state.json"
    state = json.loads(state_path.read_text())
    state["probe_expected"][0] += 1.0
    data = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    state_path.write_bytes(data)
    body = json.loads((root / "package.json").read_text())
    import hashlib

    body["payload_sha256"]["state.json"] = hashlib.sha256(data).hexdigest()
    body.pop("package_id")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    new_id = f"{body['recipe_id']}-{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"
    body["package_id"] = new_id
    (root / "package.json").write_text(json.dumps(body))
    root.rename(tmp_path / new_id)
    with pytest.raises(ModelPackageError, match="probe outputs differ"):
        load_model_package(tmp_path / new_id)


def test_anomaly_output_requires_threshold_and_interval_rule() -> None:
    with pytest.raises(ModelPackageError, match="threshold"):
        PackageOutputSpec(task=ModelTask.ANOMALY_SCORE, value_name="s")
    with pytest.raises(ModelPackageError, match="review interval"):
        PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE, value_name="s", threshold=1.0, threshold_rule="r"
        )


def test_retired_remaining_life_packages_are_refused_and_recognised(tmp_path: Path) -> None:
    manifest = write_model_package(tmp_path, _linear_build())
    path = tmp_path / manifest.package_id / "package.json"
    body = json.loads(path.read_text())
    body["output"] = {**body["output"], "task": "rul-estimate", "unit": "acquisition-interval"}
    path.write_text(json.dumps(body))
    with pytest.raises(ModelPackageError, match="retired model task"):
        load_model_package(tmp_path / manifest.package_id)
    assert is_retired_package(tmp_path, manifest.package_id)
    assert not is_retired_package(tmp_path, "missing")


def test_feature_width_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = write_model_package(tmp_path, _linear_build())
    package = load_model_package(tmp_path / manifest.package_id)
    with pytest.raises(ModelPackageError, match="feature schema"):
        package.evaluate([[1.0, 2.0]])


def test_linear_output_does_not_depend_on_batch_composition(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    coefficients = rng.normal(size=16).tolist()
    build = _linear_build(
        input=PackageInputSpec(
            step_kind=StepKind.ACQUISITION_SNAPSHOT,
            channels=("ch1",),
            feature_set_id="test-features-v1",
            feature_names=tuple(f"f{i}" for i in range(16)),
        ),
        preprocessing=AffinePreprocessing(center=(0.5,) * 16, scale=(3.0,) * 16),
        estimator_state={"coefficients": coefficients, "intercept": 1234.5},
        probe_rows=rng.normal(size=(4, 16)).tolist(),
    )
    manifest = write_model_package(tmp_path, build)
    package = load_model_package(tmp_path / manifest.package_id)
    rows = (rng.normal(size=(500, 16)) * 1000).tolist()
    batch = package.evaluate(rows)
    assert batch == tuple(package.evaluate([row])[0] for row in rows)


def test_pca_residual_decomposes_exactly_and_ignores_batch_composition(tmp_path: Path) -> None:
    rng = np.random.default_rng(5)
    basis = rng.normal(size=(3, 6))
    train = rng.normal(size=(400, 3)) @ basis + rng.normal(scale=0.01, size=(400, 6))
    mean = train.mean(axis=0)
    _, _, vt = np.linalg.svd(train - mean, full_matrices=False)
    build = PackageBuild(
        recipe_id="test-pca-v1",
        estimator_kind=EstimatorKind.PCA_RESIDUAL,
        input=PackageInputSpec(
            step_kind=StepKind.OBSERVATION_WINDOW,
            channels=("c",),
            feature_set_id="test-features-v1",
            feature_names=tuple(f"f{i}" for i in range(6)),
        ),
        output=PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="spe",
            threshold=1.0,
            threshold_rule="fixed-for-test",
            review_interval=ReviewIntervalRule(2, 1),
            provides_feature_contributions=True,
        ),
        preprocessing=AffinePreprocessing((0.0,) * 6, (1.0,) * 6),
        estimator_state={"mean": mean.tolist(), "components": vt[:3].tolist()},
        fit_rows=None,
        probe_rows=train[:4].tolist(),
        training_scope={},
        validation={},
        applicability={},
        created_at="2026-10-12T00:00:00+00:00",
        code_revision="0" * 40,
    )
    package = load_model_package(tmp_path / write_model_package(tmp_path, build).package_id)
    shifted = train[:50].copy()
    shifted[:, 4] += 3.0
    rows = shifted.tolist()
    scores = package.evaluate(rows)
    assert scores == tuple(package.evaluate([row])[0] for row in rows)
    contributions = package.feature_contributions(rows)
    assert contributions is not None
    for score, parts in zip(scores, contributions, strict=True):
        assert sum(parts.values()) == pytest.approx(score)
    assert max(contributions[0], key=contributions[0].__getitem__) == "f4"
    assert min(scores) > max(package.evaluate(train[100:150].tolist()))
