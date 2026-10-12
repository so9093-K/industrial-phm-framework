"""Explicit seven-channel electrical windows for PHM runtime and browser contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    ChannelSemanticBinding,
    MeasurementDefinition,
    ObservationWindowBuffer,
)
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_CHANNELS,
    ELECTRICAL_WINDOW_FEATURE_NAMES,
)
from industrial_phm.application.observation_window import DurableObservationWindow
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
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
from tests.support.window_analysis import START, window_event

CHANNELS = ("ia", "ib", "ic", "va", "vb", "vc", "freq")


def electrical_window(
    name: str,
    start: datetime,
    current: float = 10.0,
    *,
    point: str = "mcc-3",
    frequency: float = 60.0,
    duration_minutes: int = 5,
) -> DurableObservationWindow:
    end = start + timedelta(minutes=duration_minutes)
    buffer = ObservationWindowBuffer(
        window_id=name,
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id=point,
        expected_channel_ids=CHANNELS,
        window_start=start,
        window_end=end,
        max_buffered_events=100,
        max_future_skew_seconds=5.0,
    )
    base = int((start - START).total_seconds())
    for minute in range(duration_minutes):
        for offset, channel in enumerate(CHANNELS):
            value = frequency if channel == "freq" else (220.0 if channel[0] == "v" else current)
            event = window_event(
                "ia" if channel == "freq" else channel,
                base + minute * 60,
                value,
                (base + minute * 60) * 20 + offset * 2 + int(point != "mcc-3"),
            )
            registered = replace(event.event, measurement_point_id=point)
            if channel == "freq":
                obs = replace(
                    registered.notification.observation, channel_id="freq", node_id="ns=2;s=freq"
                )
                registered = replace(
                    registered,
                    notification=replace(registered.notification, observation=obs),
                    semantic_binding=ChannelSemanticBinding(
                        source_id="site-opcua",
                        channel_id="freq",
                        version="site-semantics-v1",
                        definition=MeasurementDefinition(
                            "frequency",
                            scope="three-phase supply voltage",
                            unit="Hz",
                            unit_evidence="explicit test fixture",
                        ),
                        interpretation_evidence="synthetic test",
                    ),
                )
            buffer.ingest(replace(event, event=registered))
    buffer.advance_watermark(end)
    return buffer.finalize(finalized_at=end)


def electrical_workspace(root: Path) -> OperationsWorkspace:
    workspace = OperationsWorkspace(root)
    initialize_operations_workspace(workspace)
    width = len(ELECTRICAL_WINDOW_FEATURE_NAMES)
    baseline = [10.0] * 3 + [220.0] * 3 + [0.0] * 3 + [60.0]
    package = write_model_package(
        workspace.models_path,
        PackageBuild(
            recipe_id="synthetic-electrical-pca-v1",
            estimator_kind=EstimatorKind.PCA_RESIDUAL,
            input=PackageInputSpec(
                step_kind=StepKind.OBSERVATION_WINDOW,
                channels=ELECTRICAL_WINDOW_CHANNELS,
                feature_set_id="electrical-window-v1",
                feature_names=ELECTRICAL_WINDOW_FEATURE_NAMES,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="spe",
                threshold=1.0,
                threshold_rule="synthetic-test",
                review_interval=ReviewIntervalRule(2, 1),
                step_period_seconds=300.0,
                provides_feature_contributions=True,
            ),
            preprocessing=AffinePreprocessing((0.0,) * width, (1.0,) * width),
            estimator_state={"mean": baseline, "components": [[1.0] + [0.0] * (width - 1)]},
            fit_rows=None,
            probe_rows=[baseline],
            training_scope={"dataset_id": "synthetic"},
            validation={"evidence_class": "synthetic-test"},
            applicability={"asset_id": ["motor-7"]},
            created_at=START.isoformat(),
            code_revision="0" * 40,
        ),
    )
    SqlitePhmAnalysisStore(workspace.phm_analysis_path).create_binding(
        PhmBinding(
            "electrical-a",
            package.package_id,
            "site-opcua",
            "motor-7",
            StepKind.OBSERVATION_WINDOW,
            START,
            recorded_replay=True,
            measurement_point_id="mcc-3",
        )
    )
    return workspace
