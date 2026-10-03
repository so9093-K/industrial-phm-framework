from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application import (
    FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
    AnalysisRun,
    CollectionDesiredState,
    FindingReviewAction,
    OperationalVibrationFeatureEvidence,
    OpcUaSourceConfig,
    RegisteredFieldFeatureAnalysis,
    RegisteredSource,
    SourceLifecycleState,
    SourceRuntimeCycleResult,
    SourceRuntimeCycleState,
    SourceSnapshotEvidence,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.contracts import DataQualityAssessment
from industrial_phm.runtime.operations_app_actions import (
    OperationsAppActions,
    OperationsDiagnosticKind,
)
from industrial_phm.runtime.operations_app_composition import resolve_operations_app_paths


def _actions(tmp_path: Path) -> OperationsAppActions:
    return OperationsAppActions(
        resolve_operations_app_paths(
            {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "workspace")}
        )
    )


def _opcua_source() -> RegisteredSource:
    return RegisteredSource(
        source_id="opcua-1",
        name="OPC UA source",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            asset_id="asset-1",
            measurement_point_id="mcc-1",
            node_mappings=(OpcUaNodeMapping(channel_id="v-r", node_id="ns=2;s=V_R"),),
            timeout_seconds=1.0,
        ),
        registered_at=datetime(2026, 10, 3, 8, 0, tzinfo=UTC),
    )


def _analysis_result() -> RegisteredFieldFeatureAnalysis:
    snapshot = SourceSnapshotEvidence(
        name="bearing.csv",
        sha256="a" * 64,
        size_bytes=128,
    )
    run = AnalysisRun(
        analysis_run_id="analysis-run-actions",
        asset_id="bearing-01",
        source_id="field-bearing-01",
        measurement_point_id="de",
        observed_start_at=datetime(2026, 10, 3, 1, 0, tzinfo=UTC),
        observed_end_at=datetime(2026, 10, 3, 1, 0, 2, tzinfo=UTC),
        started_at=datetime(2026, 10, 3, 1, 5, tzinfo=UTC),
        completed_at=datetime(2026, 10, 3, 1, 5, 1, tzinfo=UTC),
        data_quality=DataQualityAssessment(),
        source_snapshots=(snapshot,),
        capability_ids=(FIELD_VIBRATION_FEATURE_CAPABILITY_ID,),
    )
    return RegisteredFieldFeatureAnalysis(
        run=run,
        evidence=OperationalVibrationFeatureEvidence(
            evidence_id="evidence-actions",
            analysis_run_id=run.analysis_run_id,
            capability_id=FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
            feature_set_id="vibration-statistical-v1",
            feature_names=("rms", "peak"),
            values=(1.25, 2.5),
            source_snapshot_sha256=snapshot.sha256,
        ),
    )


def test_actions_own_source_registry_freshness_lifecycle_and_collection(
    tmp_path: Path,
) -> None:
    actions = _actions(tmp_path)
    source = _opcua_source()

    registered = actions.register_source(source)
    assert registered.sources == (source,)
    assert registered.lifecycles[0].state == SourceLifecycleState.REGISTERED

    policy, fresh = actions.set_freshness_policy(
        source.source_id,
        max_observation_age_seconds=15.0,
        changed_at=datetime(2026, 10, 3, 8, 1, tzinfo=UTC),
    )
    assert policy is not None
    assert policy.max_observation_age_seconds == 15.0
    assert fresh.freshness_policies == (policy,)

    lifecycle, active = actions.transition_source(
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime(2026, 10, 3, 8, 2, tzinfo=UTC),
    )
    assert lifecycle.state == SourceLifecycleState.ACTIVE
    assert active.lifecycles == (lifecycle,)

    collection, records = actions.request_collection(
        source.source_id,
        CollectionDesiredState.RUNNING,
        requested_at=datetime(2026, 10, 3, 8, 3, tzinfo=UTC),
    )
    assert collection.desired_state == CollectionDesiredState.RUNNING
    assert records == (collection,)

    cleared, state = actions.set_freshness_policy(
        source.source_id,
        max_observation_age_seconds=None,
        changed_at=datetime(2026, 10, 3, 8, 4, tzinfo=UTC),
    )
    assert cleared is None
    assert state.freshness_policies == ()


def test_actions_bridge_opcua_diagnostic_outside_marimo_event_loop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import industrial_phm.runtime.operations_app_actions as action_module

    actions = _actions(tmp_path)
    source = _opcua_source()
    registered = actions.register_source(source)
    lifecycle = registered.lifecycles[0]
    expected = SourceRuntimeCycleResult(
        source_id=source.source_id,
        state=SourceRuntimeCycleState.SKIPPED,
        executed_at=datetime(2026, 10, 3, 8, 5, tzinfo=UTC),
        lifecycle_before=lifecycle,
        lifecycle_after=lifecycle,
        message="diagnostic stub",
    )

    async def fake_cycle(*args, **kwargs):
        return expected

    monkeypatch.setattr(action_module, "run_registered_opcua_source_cycle", fake_cycle)

    result, state = actions.run_diagnostic(
        source.source_id,
        kind=OperationsDiagnosticKind.CYCLE,
    )

    assert result == expected
    assert state.sources == (source,)
    assert state.lifecycles == (lifecycle,)


def test_actions_persist_review_request_and_review_event(tmp_path: Path) -> None:
    actions = _actions(tmp_path)
    result = _analysis_result()

    finding, findings = actions.request_review(result)
    assert findings == (finding,)
    assert finding.analysis_run_id == result.run.analysis_run_id

    event, events = actions.record_review_action(
        finding,
        action=FindingReviewAction.ACKNOWLEDGE,
        note="accepted for review",
    )
    assert events == (event,)
    assert event.finding_id == finding.finding_id
    assert event.action == FindingReviewAction.ACKNOWLEDGE
    assert event.note == "accepted for review"
