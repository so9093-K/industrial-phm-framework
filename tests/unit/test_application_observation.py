from datetime import datetime

import pytest

from industrial_phm.application import (
    AssetObservationSummary,
    AssetObservationTimeline,
    ObservationValidationPolicy,
    SourceSnapshotEvidence,
)
from industrial_phm.contracts import DataQualityAssessment

def test_asset_observation_summary_preserves_operational_observation_facts() -> None:
    start = datetime.fromisoformat("2026-09-22T10:00:00+09:00")
    end = datetime.fromisoformat("2026-09-22T10:00:02+09:00")
    channels = ["vibration_x", "temperature"]
    snapshot = SourceSnapshotEvidence(
        name="pump.csv",
        sha256="a" * 64,
        size_bytes=128,
    )
    policy = ObservationValidationPolicy(
        source_timestamp_field="timestamp",
        minimum_sample_count=3,
        sampling_rate_tolerance_ratio=0.05,
    )

    summary = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export:pump-01",
        measurement_point_id="drive-end-bearing",
        channels=channels,
        sample_count=3,
        observed_start_at=start,
        observed_end_at=end,
        sampling_rate_hz=1.0,
        source_snapshot=snapshot,
        validation_policy=policy,
        data_quality=DataQualityAssessment(),
    )
    channels.append("rpm")

    assert summary.asset_id == "pump-01"
    assert summary.source_id == "field-export:pump-01"
    assert summary.measurement_point_id == "drive-end-bearing"
    assert summary.channels == ("vibration_x", "temperature")
    assert summary.sample_count == 3
    assert summary.observed_start_at == start
    assert summary.observed_end_at == end
    assert summary.sampling_rate_hz == 1.0
    assert summary.source_snapshot == snapshot
    assert summary.validation_policy == policy

def test_source_snapshot_evidence_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="64 hexadecimal"):
        SourceSnapshotEvidence(
            name="pump.csv",
            sha256="not-a-digest",
            size_bytes=128,
        )

def test_observation_validation_policy_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        ObservationValidationPolicy(
            minimum_sample_count=1,
            sampling_rate_tolerance_ratio=-0.01,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("asset_id", ""),
        ("source_id", " source "),
    ],
)
def test_asset_observation_summary_rejects_invalid_identity(
    field_name: str,
    value: str,
) -> None:
    kwargs = {
        "asset_id": "pump-01",
        "source_id": "field-export:pump-01",
        "channels": ("vibration",),
        "sample_count": 1,
        "data_quality": DataQualityAssessment(),
    }
    kwargs[field_name] = value

    with pytest.raises(ValueError):
        AssetObservationSummary(**kwargs)  # type: ignore[arg-type]

def test_asset_observation_summary_rejects_mixed_time_awareness() -> None:
    with pytest.raises(ValueError, match="timezone awareness"):
        AssetObservationSummary(
            asset_id="pump-01",
            source_id="field-export:pump-01",
            channels=("vibration",),
            sample_count=2,
            observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
            observed_end_at=datetime.fromisoformat("2026-09-22T10:00:01"),
            data_quality=DataQualityAssessment(),
        )

def test_asset_observation_summary_rejects_reversed_observation_window() -> None:
    with pytest.raises(ValueError, match="must not be after"):
        AssetObservationSummary(
            asset_id="pump-01",
            source_id="field-export:pump-01",
            channels=("vibration",),
            sample_count=2,
            observed_start_at=datetime.fromisoformat("2026-09-22T10:00:02+09:00"),
            observed_end_at=datetime.fromisoformat("2026-09-22T10:00:01+09:00"),
            data_quality=DataQualityAssessment(),
        )


def test_asset_observation_timeline_preserves_ordered_segments() -> None:
    first = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export",
        measurement_point_id="drive-end-bearing",
        channels=("vibration_x",),
        sample_count=2,
        observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T10:00:01+09:00"),
        data_quality=DataQualityAssessment(),
    )
    second = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export",
        measurement_point_id="drive-end-bearing",
        channels=("vibration_x",),
        sample_count=2,
        observed_start_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T11:00:01+09:00"),
        data_quality=DataQualityAssessment(),
    )

    timeline = AssetObservationTimeline((first, second))

    assert timeline.asset_id == "pump-01"
    assert timeline.measurement_point_id == "drive-end-bearing"
    assert timeline.segment_count == 2
    assert timeline.observed_start_at == first.observed_start_at
    assert timeline.observed_end_at == second.observed_end_at
    assert timeline.latest is second

def test_asset_observation_timeline_rejects_mixed_assets() -> None:
    first = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export",
        channels=("vibration_x",),
        sample_count=1,
        observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
        data_quality=DataQualityAssessment(),
    )
    second = AssetObservationSummary(
        asset_id="pump-02",
        source_id="field-export",
        channels=("vibration_x",),
        sample_count=1,
        observed_start_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
        data_quality=DataQualityAssessment(),
    )

    with pytest.raises(ValueError, match="share one asset_id"):
        AssetObservationTimeline((first, second))

def test_asset_observation_timeline_rejects_missing_absolute_time() -> None:
    segment = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export",
        channels=("vibration_x",),
        sample_count=2,
        sampling_rate_hz=1_000.0,
        data_quality=DataQualityAssessment(),
    )

    with pytest.raises(ValueError, match="explicit observed start/end"):
        AssetObservationTimeline((segment,))

def test_asset_observation_timeline_rejects_overlapping_segments() -> None:
    first = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export",
        channels=("vibration_x",),
        sample_count=2,
        observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T10:00:10+09:00"),
        data_quality=DataQualityAssessment(),
    )
    second = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export",
        channels=("vibration_x",),
        sample_count=2,
        observed_start_at=datetime.fromisoformat("2026-09-22T10:00:05+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T10:00:15+09:00"),
        data_quality=DataQualityAssessment(),
    )

    with pytest.raises(ValueError, match="strictly ordered and non-overlapping"):
        AssetObservationTimeline((first, second))
