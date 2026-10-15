"""Immutable, data-only model packages that operational analysis can reload (ADR-0025).

A package binds a fitted estimator to the exact input schema, preprocessing state, output
semantics, training scope and validation evidence it was built with. Loading verifies every
payload digest and re-evaluates a stored probe; a package whose outputs differ is refused rather
than silently scoring with a different model.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import numpy as np

MODEL_PACKAGE_SCHEMA_ID = "industrial-phm-model-package-v1"
_MANIFEST_NAME = "package.json"
_STATE_NAME = "state.json"
_FIT_ROWS_NAME = "fit-rows.npz"
_ID_DIGEST_LENGTH = 12

_JsonValue = str | int | float | bool | None | list[Any] | dict[str, Any]


class ModelPackageError(ValueError):
    """Raised when a model package is malformed, tampered with or not reproducible."""


class ModelTask(StrEnum):
    ANOMALY_SCORE = "anomaly-score"


# Tasks this product no longer runs. Packages and bindings that declare one stay on disk
# untouched but are neither loaded nor listed.
RETIRED_TASKS = frozenset({"rul-estimate"})


def declared_task(package_dir: Path) -> str | None:
    """The output task a package's manifest declares, read without verifying the package."""
    try:
        body = json.loads((package_dir / _MANIFEST_NAME).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    output = body.get("output") if isinstance(body, dict) else None
    task = output.get("task") if isinstance(output, dict) else None
    return task if isinstance(task, str) else None


def is_retired_package(models_root: Path, package_id: str) -> bool:
    return declared_task(models_root / package_id) in RETIRED_TASKS


class StepKind(StrEnum):
    OBSERVATION_WINDOW = "observation-window"
    ACQUISITION_SNAPSHOT = "acquisition-snapshot"


class EstimatorKind(StrEnum):
    """Closed set of restorable estimators; each restores from arrays, never pickle."""

    ISOLATION_FOREST_REFIT = "isolation-forest-refit-v1"
    LINEAR = "linear-v1"
    PCA_RESIDUAL = "pca-residual-v1"
    LSTM_AUTOENCODER = "lstm-autoencoder-v1"


@dataclass(frozen=True, slots=True)
class PackageInputSpec:
    """What one analysis step must provide before the package can evaluate it."""

    step_kind: StepKind
    channels: Sequence[str]
    feature_set_id: str
    feature_names: Sequence[str]
    sampling_rate_hz: float | None = None
    samples_per_step: int | None = None
    sequence_length: int = 1

    def __post_init__(self) -> None:
        if _bad_int(self.sequence_length, minimum=1) or self.sequence_length > 4096:
            raise ModelPackageError("sequence_length must be between 1 and 4096")
        if self.sequence_length > 1 and self.step_kind is not StepKind.ACQUISITION_SNAPSHOT:
            raise ModelPackageError("sequence packages currently require acquisition snapshots")
        if not isinstance(self.step_kind, StepKind):
            raise ModelPackageError("step_kind must be a StepKind")
        object.__setattr__(self, "channels", _names(self.channels, "channels"))
        _text(self.feature_set_id, "feature_set_id")
        object.__setattr__(self, "feature_names", _names(self.feature_names, "feature_names"))
        if self.sampling_rate_hz is not None and not (
            math.isfinite(self.sampling_rate_hz) and self.sampling_rate_hz > 0
        ):
            raise ModelPackageError("sampling_rate_hz must be positive and finite")
        if self.samples_per_step is not None and (
            isinstance(self.samples_per_step, bool)
            or not isinstance(self.samples_per_step, int)
            or self.samples_per_step < 1
        ):
            raise ModelPackageError("samples_per_step must be a positive integer")


@dataclass(frozen=True, slots=True)
class ReviewIntervalRule:
    """Consecutive threshold crossings that open a review interval, and the gap that closes it."""

    min_consecutive_steps: int = 2
    max_gap_steps: int = 1

    def __post_init__(self) -> None:
        if _bad_int(self.min_consecutive_steps, minimum=1):
            raise ModelPackageError("min_consecutive_steps must be a positive integer")
        if _bad_int(self.max_gap_steps, minimum=0):
            raise ModelPackageError("max_gap_steps must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class PackageOutputSpec:
    """Task-specific meaning of the evaluated value."""

    task: ModelTask
    value_name: str
    threshold: float | None = None
    threshold_rule: str | None = None
    review_interval: ReviewIntervalRule | None = None
    step_period_seconds: float | None = None
    provides_feature_contributions: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.task, ModelTask):
            raise ModelPackageError("task must be a ModelTask")
        _text(self.value_name, "value_name")
        if self.threshold is None or not math.isfinite(self.threshold):
            raise ModelPackageError("anomaly-score packages need a finite threshold")
        _text(self.threshold_rule, "threshold_rule")
        if self.review_interval is None:
            raise ModelPackageError("anomaly-score packages need a review interval rule")
        if self.step_period_seconds is not None and not (
            math.isfinite(self.step_period_seconds) and self.step_period_seconds > 0
        ):
            raise ModelPackageError("step_period_seconds must be positive and finite")


@dataclass(frozen=True, slots=True)
class ModelPackageManifest:
    """Everything needed to reload, verify and explain one fitted package."""

    package_id: str
    recipe_id: str
    estimator_kind: EstimatorKind
    input: PackageInputSpec
    output: PackageOutputSpec
    training_scope: Mapping[str, _JsonValue]
    validation: Mapping[str, _JsonValue]
    applicability: Mapping[str, Sequence[str]]
    runtime: Mapping[str, str]
    payload_sha256: Mapping[str, str]
    probe_tolerance: float
    created_at: str
    code_revision: str
    schema_id: str = field(default=MODEL_PACKAGE_SCHEMA_ID)

    def __post_init__(self) -> None:
        if self.schema_id != MODEL_PACKAGE_SCHEMA_ID:
            raise ModelPackageError(f"unsupported model package schema: {self.schema_id!r}")
        _text(self.package_id, "package_id")
        _text(self.recipe_id, "recipe_id")
        if not isinstance(self.estimator_kind, EstimatorKind):
            raise ModelPackageError("estimator_kind must be an EstimatorKind")
        if (
            self.estimator_kind is not EstimatorKind.LSTM_AUTOENCODER
            and self.input.sequence_length != 1
        ):
            raise ModelPackageError("only LSTM estimators currently consume sequence inputs")
        if not math.isfinite(self.probe_tolerance) or self.probe_tolerance < 0:
            raise ModelPackageError("probe_tolerance must be finite and non-negative")
        _text(self.created_at, "created_at")
        _text(self.code_revision, "code_revision")
        for name, digest in self.payload_sha256.items():
            _text(name, "payload name")
            if "/" in name or name.startswith(".") or name == _MANIFEST_NAME:
                raise ModelPackageError(f"invalid payload name: {name!r}")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ModelPackageError(f"invalid payload digest for {name!r}")
        object.__setattr__(self, "training_scope", MappingProxyType(dict(self.training_scope)))
        object.__setattr__(self, "validation", MappingProxyType(dict(self.validation)))
        object.__setattr__(
            self,
            "applicability",
            MappingProxyType({k: _names(v, k) for k, v in self.applicability.items()}),
        )
        object.__setattr__(self, "runtime", MappingProxyType(dict(self.runtime)))
        object.__setattr__(self, "payload_sha256", MappingProxyType(dict(self.payload_sha256)))


@dataclass(frozen=True, slots=True)
class AffinePreprocessing:
    """Train-fitted ``(x - center) / scale`` applied before the estimator."""

    center: Sequence[float]
    scale: Sequence[float]

    def __post_init__(self) -> None:
        center = tuple(float(v) for v in self.center)
        scale = tuple(float(v) for v in self.scale)
        if not center or len(center) != len(scale):
            raise ModelPackageError("affine center and scale must have the same non-zero length")
        if not all(math.isfinite(v) for v in center + scale) or any(v <= 0 for v in scale):
            raise ModelPackageError("affine state must be finite with positive scale")
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "scale", scale)

    def transform(self, rows: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
        # Same per-element Python float arithmetic as the research PreprocessingState.
        out = []
        for row in rows:
            if len(row) != len(self.center):
                raise ModelPackageError("feature row width does not match preprocessing state")
            out.append(
                tuple(
                    (float(v) - c) / s for v, c, s in zip(row, self.center, self.scale, strict=True)
                )
            )
        return tuple(out)


@dataclass(frozen=True, slots=True)
class PackageBuild:
    """Inputs for :func:`write_model_package`; the package ID is derived, never chosen."""

    recipe_id: str
    estimator_kind: EstimatorKind
    input: PackageInputSpec
    output: PackageOutputSpec
    preprocessing: AffinePreprocessing
    estimator_state: Mapping[str, _JsonValue]
    fit_rows: Sequence[Sequence[float]] | None
    probe_rows: Sequence[Sequence[float]]
    training_scope: Mapping[str, _JsonValue]
    validation: Mapping[str, _JsonValue]
    applicability: Mapping[str, Sequence[str]]
    created_at: str
    code_revision: str
    probe_tolerance: float = 0.0


class LoadedModelPackage:
    """A verified package that evaluates raw feature rows into task values."""

    def __init__(
        self,
        manifest: ModelPackageManifest,
        preprocessing: AffinePreprocessing,
        evaluate_transformed: Callable[[np.ndarray], np.ndarray],
        contributions_transformed: Callable[[np.ndarray], np.ndarray] | None = None,
    ) -> None:
        self.manifest = manifest
        self._preprocessing = preprocessing
        self._evaluate = evaluate_transformed
        self._contributions = contributions_transformed

    @property
    def package_id(self) -> str:
        return self.manifest.package_id

    def evaluate(self, rows: Sequence[Sequence[float]]) -> tuple[float, ...]:
        """Return one task value per raw (untransformed) feature row."""
        width = len(self.manifest.input.feature_names) * self.manifest.input.sequence_length
        if not rows or any(len(row) != width for row in rows):
            raise ModelPackageError("feature rows must match the package feature schema")
        transformed = self._transform(rows)
        values = tuple(float(v) for v in self._evaluate(transformed))
        if len(values) != len(rows) or not all(math.isfinite(v) for v in values):
            raise ModelPackageError("package evaluation produced invalid values")
        return values

    def _transform(self, rows: Sequence[Sequence[float]]) -> np.ndarray:
        spec = self.manifest.input
        width = len(spec.feature_names)
        steps = [row[i : i + width] for row in rows for i in range(0, len(row), width)]
        values = np.asarray(self._preprocessing.transform(steps), dtype=np.float64)
        return values.reshape(len(rows), spec.sequence_length * width)

    def feature_contributions(
        self, rows: Sequence[Sequence[float]]
    ) -> tuple[dict[str, float], ...] | None:
        """Per-feature parts of the value, only for estimators whose value decomposes."""
        if self._contributions is None:
            return None
        transformed = self._transform(rows)
        names = self.manifest.input.feature_names
        return tuple(
            {name: float(v) for name, v in zip(names, row, strict=True)}
            for row in self._contributions(transformed)
        )


def write_model_package(models_root: Path, build: PackageBuild) -> ModelPackageManifest:
    """Fit-free materialization: derive the package ID, write atomically, then verify by reload."""
    payload: dict[str, bytes] = {}
    state: dict[str, Any] = {
        "preprocessing": {
            "center": list(build.preprocessing.center),
            "scale": list(build.preprocessing.scale),
        },
        "estimator": dict(build.estimator_state),
        "probe_rows": [[float(v) for v in row] for row in build.probe_rows],
    }
    if build.estimator_kind is EstimatorKind.ISOLATION_FOREST_REFIT:
        if not build.fit_rows:
            raise ModelPackageError("Isolation Forest refit packages must store their fit rows")
        buffer = io.BytesIO()
        np.savez(buffer, rows=np.asarray(build.fit_rows, dtype=np.float64))
        payload[_FIT_ROWS_NAME] = buffer.getvalue()
    elif build.fit_rows is not None:
        raise ModelPackageError("only refit estimators store fit rows")
    if not build.probe_rows:
        raise ModelPackageError("a package needs probe rows")

    restored, _ = _restore(build.estimator_kind, state["estimator"], payload)
    preprocessing = build.preprocessing
    width = len(build.input.feature_names)
    if any(len(row) != width * build.input.sequence_length for row in build.probe_rows):
        raise ModelPackageError("probe rows must include the entire input sequence")
    probe_steps = [
        row[i : i + width] for row in build.probe_rows for i in range(0, len(row), width)
    ]
    probe_transformed = np.asarray(preprocessing.transform(probe_steps), dtype=np.float64).reshape(
        len(build.probe_rows), width * build.input.sequence_length
    )
    state["probe_expected"] = [float(v) for v in restored(probe_transformed)]
    payload[_STATE_NAME] = _canonical(state).encode("utf-8")

    runtime = _runtime_versions()
    if build.estimator_kind is EstimatorKind.LSTM_AUTOENCODER:
        from importlib import import_module

        runtime["torch"] = str(import_module("torch").__version__)
    body: dict[str, Any] = {
        "schema_id": MODEL_PACKAGE_SCHEMA_ID,
        "recipe_id": build.recipe_id,
        "estimator_kind": build.estimator_kind.value,
        "input": _input_to_json(build.input),
        "output": _output_to_json(build.output),
        "training_scope": dict(build.training_scope),
        "validation": dict(build.validation),
        "applicability": {k: list(v) for k, v in build.applicability.items()},
        "runtime": runtime,
        "payload_sha256": {name: _sha256(data) for name, data in sorted(payload.items())},
        "probe_tolerance": build.probe_tolerance,
        "created_at": build.created_at,
        "code_revision": build.code_revision,
    }
    package_id = f"{build.recipe_id}-{_sha256(_canonical(body).encode())[:_ID_DIGEST_LENGTH]}"
    body["package_id"] = package_id
    manifest = _manifest_from_json(body)

    destination = models_root / package_id
    if destination.exists():
        load_model_package(destination)  # identical content already present; verify it
        return manifest
    models_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{package_id}.", dir=models_root))
    try:
        for name, data in payload.items():
            (staging / name).write_bytes(data)
        (staging / _MANIFEST_NAME).write_text(_canonical(body) + "\n", encoding="utf-8")
        for item in staging.iterdir():
            with item.open("rb") as handle:
                os.fsync(handle.fileno())
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    load_model_package(destination)
    return manifest


def load_model_package(path: Path) -> LoadedModelPackage:
    """Verify digests and probe outputs, then return an evaluating package."""
    try:
        body = json.loads((path / _MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelPackageError(f"model package manifest unreadable: {path.name}") from error
    if not isinstance(body, dict):
        raise ModelPackageError("model package manifest must be an object")
    manifest = _manifest_from_json(body)
    expected_id = body.copy()
    expected_id.pop("package_id", None)
    derived = (
        f"{manifest.recipe_id}-{_sha256(_canonical(expected_id).encode())[:_ID_DIGEST_LENGTH]}"
    )
    if derived != manifest.package_id or path.name != manifest.package_id:
        raise ModelPackageError("model package ID does not match its manifest content")

    payload: dict[str, bytes] = {}
    for name, digest in manifest.payload_sha256.items():
        try:
            data = (path / name).read_bytes()
        except OSError as error:
            raise ModelPackageError(f"model package payload missing: {name}") from error
        if _sha256(data) != digest:
            raise ModelPackageError(f"model package payload digest mismatch: {name}")
        payload[name] = data
    try:
        state = json.loads(payload[_STATE_NAME])
    except (KeyError, json.JSONDecodeError) as error:
        raise ModelPackageError("model package state unreadable") from error

    preprocessing = AffinePreprocessing(
        center=state["preprocessing"]["center"], scale=state["preprocessing"]["scale"]
    )
    evaluate, contributions = _restore(manifest.estimator_kind, state["estimator"], payload)
    package = LoadedModelPackage(manifest, preprocessing, evaluate, contributions)
    observed = package.evaluate(state["probe_rows"])
    expected = state["probe_expected"]
    if len(observed) != len(expected) or any(
        abs(o - float(e)) > manifest.probe_tolerance
        for o, e in zip(observed, expected, strict=True)
    ):
        raise ModelPackageError(
            "model package probe outputs differ from the recorded outputs; "
            f"runtime {_runtime_versions()} vs recorded {dict(manifest.runtime)}"
        )
    return package


_Evaluate = Callable[[np.ndarray], np.ndarray]


def _restore(
    kind: EstimatorKind, state: Mapping[str, Any], payload: Mapping[str, bytes]
) -> tuple[_Evaluate, _Evaluate | None]:
    if kind is EstimatorKind.LSTM_AUTOENCODER:
        from industrial_phm.models.package_lstm import restore_lstm_estimator

        return restore_lstm_estimator(kind, state)
    if kind is EstimatorKind.LINEAR:
        coefficients = np.asarray(state["coefficients"], dtype=np.float64)
        intercept = float(state["intercept"])
        if coefficients.ndim != 1:
            raise ModelPackageError("linear coefficients must be a vector")
        # Elementwise products reduced per row: unlike a BLAS matrix-vector product, the
        # summation order cannot depend on how many rows are evaluated together.
        return (lambda rows: (rows * coefficients).sum(axis=1) + intercept), None
    if kind is EstimatorKind.PCA_RESIDUAL:
        mean = np.asarray(state["mean"], dtype=np.float64)
        components = np.asarray(state["components"], dtype=np.float64)
        if components.ndim != 2 or components.shape[1] != mean.shape[0]:
            raise ModelPackageError("PCA components must be k x d with a d-wide mean")

        def residual_squares(rows: np.ndarray) -> np.ndarray:
            # Broadcast products reduced per row (no BLAS), so a row's value never depends
            # on the other rows evaluated with it.
            centered = rows - mean
            scores = (centered[:, None, :] * components[None, :, :]).sum(axis=2)
            reconstruction = (scores[:, :, None] * components[None, :, :]).sum(axis=1)
            residual = centered - reconstruction
            return cast(np.ndarray, residual * residual)

        # Squared prediction error (SPE) and its exact per-feature decomposition.
        return (lambda rows: residual_squares(rows).sum(axis=1)), residual_squares
    if kind is EstimatorKind.ISOLATION_FOREST_REFIT:
        from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

        with np.load(io.BytesIO(payload[_FIT_ROWS_NAME]), allow_pickle=False) as arrays:
            rows = np.asarray(arrays["rows"], dtype=np.float64)
        estimator = IsolationForest(
            n_estimators=int(state["n_estimators"]),
            max_samples=state["max_samples"],
            contamination=state["contamination"],
            max_features=state["max_features"],
            bootstrap=bool(state["bootstrap"]),
            n_jobs=1,
            random_state=int(state["random_seed"]),
        )
        estimator.fit(rows)
        # Higher score means more anomalous, matching FittedIsolationForest.score.
        return (lambda x: -cast(np.ndarray, estimator.score_samples(x))), None
    raise ModelPackageError(f"unsupported estimator kind: {kind!r}")  # pragma: no cover


def _manifest_from_json(body: Mapping[str, Any]) -> ModelPackageManifest:
    try:
        return ModelPackageManifest(
            schema_id=body["schema_id"],
            package_id=body.get("package_id", "pending"),
            recipe_id=body["recipe_id"],
            estimator_kind=EstimatorKind(body["estimator_kind"]),
            input=_input_from_json(body["input"]),
            output=_output_from_json(body["output"]),
            training_scope=body["training_scope"],
            validation=body["validation"],
            applicability=body["applicability"],
            runtime=body["runtime"],
            payload_sha256=body["payload_sha256"],
            probe_tolerance=float(body["probe_tolerance"]),
            created_at=body["created_at"],
            code_revision=body["code_revision"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ModelPackageError):
            raise
        raise ModelPackageError(f"malformed model package manifest: {error}") from error


def _input_to_json(spec: PackageInputSpec) -> dict[str, Any]:
    body: dict[str, Any] = {
        "step_kind": spec.step_kind.value,
        "channels": list(spec.channels),
        "feature_set_id": spec.feature_set_id,
        "feature_names": list(spec.feature_names),
        "sampling_rate_hz": spec.sampling_rate_hz,
        "samples_per_step": spec.samples_per_step,
    }

    if spec.sequence_length != 1:
        body["sequence_length"] = spec.sequence_length
    return body


def _input_from_json(raw: Mapping[str, Any]) -> PackageInputSpec:
    return PackageInputSpec(
        step_kind=StepKind(raw["step_kind"]),
        channels=raw["channels"],
        feature_set_id=raw["feature_set_id"],
        feature_names=raw["feature_names"],
        sampling_rate_hz=raw["sampling_rate_hz"],
        samples_per_step=raw["samples_per_step"],
        sequence_length=raw.get("sequence_length", 1),
    )


def _output_to_json(spec: PackageOutputSpec) -> dict[str, Any]:
    rule = spec.review_interval
    return {
        "task": spec.task.value,
        "value_name": spec.value_name,
        "threshold": spec.threshold,
        "threshold_rule": spec.threshold_rule,
        "review_interval": None
        if rule is None
        else {
            "min_consecutive_steps": rule.min_consecutive_steps,
            "max_gap_steps": rule.max_gap_steps,
        },
        # Always null since remaining-life packages were retired; kept so manifests, and the
        # package IDs derived from them, stay byte-identical.
        "unit": None,
        "endpoint_semantics": None,
        "step_period_seconds": spec.step_period_seconds,
        "provides_feature_contributions": spec.provides_feature_contributions,
    }


def _output_from_json(raw: Mapping[str, Any]) -> PackageOutputSpec:
    if raw["task"] in RETIRED_TASKS or raw.get("unit") is not None:
        raise ModelPackageError(f"retired model task: {raw['task']}")
    rule = raw["review_interval"]
    return PackageOutputSpec(
        task=ModelTask(raw["task"]),
        value_name=raw["value_name"],
        threshold=raw["threshold"],
        threshold_rule=raw["threshold_rule"],
        review_interval=None if rule is None else ReviewIntervalRule(**rule),
        step_period_seconds=raw["step_period_seconds"],
        provides_feature_contributions=bool(raw["provides_feature_contributions"]),
    )


def _runtime_versions() -> dict[str, str]:
    import platform

    import sklearn  # type: ignore[import-untyped]

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scikit-learn": sklearn.__version__,
    }


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _names(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    names = tuple(values)
    if not names or len(set(names)) != len(names):
        raise ModelPackageError(f"{field_name} must contain unique values")
    for name in names:
        _text(name, field_name)
    return names


def _text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ModelPackageError(f"{field_name} must be a trimmed non-empty string")


def _bad_int(value: object, *, minimum: int) -> bool:
    return isinstance(value, bool) or not isinstance(value, int) or value < minimum
