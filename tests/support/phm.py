"""Synthetic waveform streams and linear packages for PHM monitoring tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    SqliteAcquisitionSnapshotRepository,
    file_sha256,
)
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
from industrial_phm.application.phm_runner import PackageCache, run_snapshot_bindings
from industrial_phm.features.vibration import vibration_feature_names
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
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    initialize_operations_workspace,
)

T0 = datetime(2026, 10, 12, tzinfo=UTC)
CHANNELS = ("Horizontal_vibration_signals", "Vertical_vibration_signals")
SAMPLES = 64


def _linear(
    workspace: OperationsWorkspace,
    recipe: str,
    output: PackageOutputSpec,
    weights: dict[str, float],
    intercept: float,
) -> str:
    names = vibration_feature_names(CHANNELS)
    coefficients = [weights.get(name, 0.0) for name in names]
    manifest = write_model_package(
        workspace.models_path,
        PackageBuild(
            recipe_id=recipe,
            estimator_kind=EstimatorKind.LINEAR,
            input=PackageInputSpec(
                step_kind=StepKind.ACQUISITION_SNAPSHOT,
                channels=CHANNELS,
                feature_set_id="vibration-statistical-v1",
                feature_names=names,
                sampling_rate_hz=1000.0,
                samples_per_step=SAMPLES,
            ),
            output=output,
            preprocessing=AffinePreprocessing((0.0,) * len(names), (1.0,) * len(names)),
            estimator_state={"coefficients": coefficients, "intercept": intercept},
            fit_rows=None,
            probe_rows=[[1.0] * len(names)],
            training_scope={
                "dataset_id": "synthetic",
                "partition": "train",
                "asset_ids": ["train-a"],
            },
            validation={
                "evidence_class": "synthetic-test-evidence",
                "mean_asset_mean_absolute_error": 12.5,
                "per_asset": [
                    {
                        "asset_id": "bearing-a",
                        "mean_absolute_error": 10.0,
                        "mean_signed_error": -3.0,
                    }
                ],
            },
            applicability={"operating_condition": ["c1"]},
            created_at=T0.isoformat(),
            code_revision="0" * 40,
        ),
    )
    return manifest.package_id


def phm_workspace(root: Path, *, bind: bool = True) -> OperationsWorkspace:
    """Workspace with two anomaly packages (horizontal and vertical RMS) on one bearing stream."""
    workspace = OperationsWorkspace(root)
    initialize_operations_workspace(workspace)
    packages = []
    for package_id, channel in (
        ("synthetic-rms-score-v1", "Horizontal"),
        ("synthetic-vertical-score-v1", "Vertical"),
    ):
        packages.append(
            _linear(
                workspace,
                package_id,
                PackageOutputSpec(
                    task=ModelTask.ANOMALY_SCORE,
                    value_name=channel[0].lower() + "_rms",
                    threshold=2.0,
                    threshold_rule="fixed-for-test",
                    review_interval=ReviewIntervalRule(2, 1),
                    step_period_seconds=60.0,
                ),
                {f"feature.{channel}_vibration_signals.rms": 1.0},
                0.0,
            )
        )
    if not bind:
        return workspace
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    for binding_id, package_id in zip(("anomaly-a", "anomaly-b"), packages, strict=True):
        store.create_binding(
            PhmBinding(
                binding_id, package_id, "bench", "bearing-a", StepKind.ACQUISITION_SNAPSHOT, T0
            )
        )
    return workspace


def retire_into(workspace: OperationsWorkspace, binding_id: str = "rul-old") -> str:
    """A leftover remaining-life package and binding, as an older workspace still holds them."""
    package_id = "old-rul-package"
    folder = workspace.models_path / package_id
    folder.mkdir(parents=True)
    (folder / "package.json").write_text(
        '{"package_id": "old-rul-package", "input": {"step_kind": "acquisition-snapshot"},'
        ' "output": {"task": "rul-estimate", "unit": "acquisition-interval"}}'
    )
    SqlitePhmAnalysisStore(workspace.phm_analysis_path).create_binding(
        PhmBinding(binding_id, package_id, "bench", "bearing-a", StepKind.ACQUISITION_SNAPSHOT, T0)
    )
    return package_id


def deliver(workspace: OperationsWorkspace, waveforms: Path, ordinal: int, scale: float) -> None:
    waveforms.mkdir(parents=True, exist_ok=True)
    path = waveforms / f"{ordinal}.csv"
    rows = [f"{scale * ((i % 4) - 1.5):.6f},{(i % 3) - 1.0 + 0.01 * i:.6f}" for i in range(SAMPLES)]
    path.write_text(",".join(CHANNELS) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path).record(
        AcquisitionSnapshot(
            source_id="bench",
            asset_id="bearing-a",
            ordinal=ordinal,
            file_path=path.resolve(),
            sha256=file_sha256(path),
            channels=CHANNELS,
            sampling_rate_hz=1000.0,
            sample_count=SAMPLES,
            delivered_at=T0 + timedelta(minutes=ordinal),
            replay=True,
            acquisition_period_seconds=60.0,
            metadata={"operating_condition": "c1"},
        )
    )


def analyze(workspace: OperationsWorkspace) -> None:
    run_snapshot_bindings(
        SqlitePhmAnalysisStore(workspace.phm_analysis_path),
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        PackageCache(workspace.models_path),
        now=lambda: T0,
    )


class ScriptedModel:
    """Stands in for the local model: answers drafts in order; the reviewer finds nothing.

    Patch it over ``industrial_phm.genai.phm_answer.complete_json`` so every check, rewrite
    and fallback around the model runs for real.
    """

    def __init__(self, *drafts: dict[str, Any]) -> None:
        self.drafts = list(drafts)
        self.requests: list[list[dict[str, str]]] = []

    def __call__(
        self,
        provider: object,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        if "causal" in schema["properties"]:
            return {
                "causal": False,
                "trend": False,
                "contradiction": False,
                "verdict": False,
                "answers_question": True,
                "quote": "",
            }
        self.requests.append(messages)
        return self.drafts.pop(0) if len(self.drafts) > 1 else dict(self.drafts[0])
