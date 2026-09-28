from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    AnalysisRun,
    AssetIdentity,
    AssetObservationSummary,
    FileSourceConfig,
    FindingReviewAction,
    FindingReviewEvent,
    OperationalFinding,
    RegisteredSource,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceReceiptEvidence,
    build_operations_overview,
)
from industrial_phm.application.asset_detail import (
    AssetEvidenceEvent,
    AssetEvidenceEventKind,
    AssetEvidenceTimeBasis,
    build_asset_detail,
    list_operational_asset_identities,
)
from industrial_phm.contracts import DataQualityAssessment

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _source(
    asset_id: str = "pump-01",
    *,
    source_id: str = "source-a",
) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=source_id,
        config=FileSourceConfig(
            source_path=f"data/{source_id}.csv",
            asset_id=asset_id,
            measurement_point_id="drive-end",
            channel_columns=("vibration_x",),
            sampling_rate_hz=1_000.0,
        ),
        registered_at=NOW - timedelta(hours=2),
    )


def _overview(source: RegisteredSource):
    lifecycle = SourceLifecycleRecord(
        source_id=source.source_id,
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW - timedelta(hours=1),
    )
    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        observed_at=NOW - timedelta(minutes=6),
        received_at=NOW - timedelta(minutes=5),
    )
    policy = SourceFreshnessPolicy(
        source_id=source.source_id,
        max_observation_age_seconds=3_600.0,
        changed_at=NOW - timedelta(hours=1),
    )
    return build_operations_overview(
        sources=(source,),
        lifecycle_records=(lifecycle,),
        receipts=(receipt,),
        freshness_policies=(policy,),
        connection_attempts=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        as_of=NOW,
    )


def _run(asset_id: str = "pump-01") -> AnalysisRun:
    return AnalysisRun(
        analysis_run_id="analysis-1",
        asset_id=asset_id,
        source_id="source-a",
        measurement_point_id="drive-end",
        observed_start_at=NOW - timedelta(minutes=6),
        observed_end_at=NOW - timedelta(minutes=4),
        started_at=NOW - timedelta(minutes=3),
        completed_at=NOW - timedelta(minutes=2),
        data_quality=DataQualityAssessment(),
        capability_ids=(
            "field-vibration-statistical-features-v1",
            "secondary-capability-v1",
        ),
    )


def _finding(asset_id: str = "pump-01") -> OperationalFinding:
    return OperationalFinding(
        finding_id="finding-1",
        analysis_run_id="analysis-1",
        asset_id=asset_id,
        measurement_point_id="drive-end",
        observed_at=NOW - timedelta(minutes=1),
        capability_id="field-vibration-statistical-features-v1",
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=("evidence-1",),
    )


def test_operational_asset_identity_union_keeps_historical_assets() -> None:
    source = _source()
    identities = list_operational_asset_identities(
        sources=(source,),
        analysis_runs=(_run("pump-historical"),),
        findings=(_finding("pump-finding"),),
    )

    assert identities == (
        AssetIdentity("pump-01"),
        AssetIdentity("pump-finding"),
        AssetIdentity("pump-historical"),
    )


def test_asset_detail_filters_identity_and_builds_evidence_timeline() -> None:
    source = _source()
    observation = AssetObservationSummary(
        asset_id="pump-01",
        source_id="source-a",
        measurement_point_id="drive-end",
        channels=("vibration_x",),
        sample_count=3,
        observed_start_at=NOW - timedelta(minutes=6),
        observed_end_at=NOW - timedelta(minutes=4),
        data_quality=DataQualityAssessment(),
    )
    run = _run()
    finding = _finding()
    review = FindingReviewEvent(
        event_id="review-1",
        finding_id=finding.finding_id,
        action=FindingReviewAction.ACKNOWLEDGE,
        recorded_at=NOW,
    )

    detail = build_asset_detail(
        AssetIdentity("pump-01"),
        sources=(source, _source("pump-other", source_id="source-other")),
        overview=_overview(source),
        latest_observations=(observation,),
        analysis_runs=(run, _run("pump-other")),
        findings=(finding, _finding("pump-other")),
        review_events=(review,),
    )

    assert detail.asset_identity == AssetIdentity("pump-01")
    assert [item.source.source_id for item in detail.source_contexts] == ["source-a"]
    assert detail.latest_observations == (observation,)
    assert detail.analysis_runs == (run,)
    assert detail.findings == (finding,)
    assert detail.review_events == (review,)

    kinds = [item.kind for item in detail.timeline.events]
    assert AssetEvidenceEventKind.SOURCE_REGISTERED in kinds
    assert AssetEvidenceEventKind.SOURCE_LIFECYCLE_CHANGED in kinds
    assert AssetEvidenceEventKind.SOURCE_OBSERVED in kinds
    assert AssetEvidenceEventKind.PLATFORM_RECEIVED in kinds
    assert AssetEvidenceEventKind.OBSERVATION_WINDOW in kinds
    assert AssetEvidenceEventKind.ANALYSIS_EXECUTED in kinds
    assert kinds.count(AssetEvidenceEventKind.CAPABILITY_EVIDENCE) == 2
    assert AssetEvidenceEventKind.FINDING_OBSERVED in kinds
    assert AssetEvidenceEventKind.REVIEW_ACTION in kinds


def test_asset_evidence_event_rejects_mismatched_clock_semantics() -> None:
    with pytest.raises(ValueError, match="source-time"):
        AssetEvidenceEvent(
            event_id="source:source-a:observed",
            kind=AssetEvidenceEventKind.SOURCE_OBSERVED,
            time_basis=AssetEvidenceTimeBasis.PLATFORM_RECEIPT_TIME,
            event_at=NOW,
            source_id="source-a",
        )


def test_asset_timeline_orders_execution_before_capability_at_same_time() -> None:
    source = _source()
    detail = build_asset_detail(
        AssetIdentity("pump-01"),
        sources=(source,),
        overview=_overview(source),
        analysis_runs=(_run(),),
    )

    same_time = tuple(
        item.kind for item in detail.timeline.events if item.event_at == NOW - timedelta(minutes=2)
    )

    assert same_time == (
        AssetEvidenceEventKind.ANALYSIS_EXECUTED,
        AssetEvidenceEventKind.CAPABILITY_EVIDENCE,
        AssetEvidenceEventKind.CAPABILITY_EVIDENCE,
    )


def test_asset_timeline_keeps_source_and_platform_clocks_separate() -> None:
    source = _source()
    detail = build_asset_detail(
        AssetIdentity("pump-01"),
        sources=(source,),
        overview=_overview(source),
    )

    source_observed = next(
        item
        for item in detail.timeline.events
        if item.kind == AssetEvidenceEventKind.SOURCE_OBSERVED
    )
    received = next(
        item
        for item in detail.timeline.events
        if item.kind == AssetEvidenceEventKind.PLATFORM_RECEIVED
    )

    assert source_observed.time_basis == AssetEvidenceTimeBasis.SOURCE_TIME
    assert source_observed.event_at == NOW - timedelta(minutes=6)
    assert received.time_basis == AssetEvidenceTimeBasis.PLATFORM_RECEIPT_TIME
    assert received.event_at == NOW - timedelta(minutes=5)
    assert source_observed.event_id != received.event_id


def test_naive_source_time_is_preserved_as_unplaced_evidence() -> None:
    source = _source()
    lifecycle = SourceLifecycleRecord(
        source_id=source.source_id,
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW - timedelta(hours=1),
    )
    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        observed_at=datetime(2026, 9, 27, 9, 54),
        received_at=NOW - timedelta(minutes=5),
    )
    overview = build_operations_overview(
        sources=(source,),
        lifecycle_records=(lifecycle,),
        receipts=(receipt,),
        freshness_policies=(),
        connection_attempts=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        as_of=NOW,
    )

    detail = build_asset_detail(
        AssetIdentity("pump-01"),
        sources=(source,),
        overview=overview,
    )

    source_observed = next(
        item
        for item in detail.timeline.unplaced_events
        if item.kind == AssetEvidenceEventKind.SOURCE_OBSERVED
    )
    assert source_observed.event_at == datetime(2026, 9, 27, 9, 54)
    assert source_observed.comparable_at is None
    assert all(
        item.kind != AssetEvidenceEventKind.SOURCE_OBSERVED for item in detail.timeline.events
    )


def test_observation_without_absolute_time_remains_unplaced() -> None:
    source = _source()
    observation = AssetObservationSummary(
        asset_id="pump-01",
        source_id="source-a",
        measurement_point_id="drive-end",
        channels=("vibration_x",),
        sample_count=32,
        sampling_rate_hz=1_000.0,
        data_quality=DataQualityAssessment(),
    )

    detail = build_asset_detail(
        AssetIdentity("pump-01"),
        sources=(source,),
        overview=_overview(source),
        latest_observations=(observation,),
    )

    event = next(
        item
        for item in detail.timeline.unplaced_events
        if item.kind == AssetEvidenceEventKind.OBSERVATION_WINDOW
    )
    assert event.event_at is None
    assert event.window_start_at is None
    assert event.window_end_at is None


def test_asset_detail_does_not_expose_condition_or_risk_verdict() -> None:
    source = _source()
    detail = build_asset_detail(
        AssetIdentity("pump-01"),
        sources=(source,),
        overview=_overview(source),
    )

    assert not hasattr(detail, "health_score")
    assert not hasattr(detail, "condition")
    assert not hasattr(detail, "risk")
    assert not hasattr(detail, "rul")
