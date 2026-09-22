from datetime import datetime

import pytest

from industrial_phm.application import AssetObservationSummary
from industrial_phm.contracts import DataQualityAssessment


def test_asset_observation_summary_preserves_operational_observation_facts() -> None:
    start = datetime.fromisoformat("2026-09-22T10:00:00+09:00")
    end = datetime.fromisoformat("2026-09-22T10:00:02+09:00")
    channels = ["vibration_x", "temperature"]

    summary = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field-export:pump-01",
        measurement_point_id="drive-end-bearing",
        channels=channels,
        sample_count=3,
        observed_start_at=start,
        observed_end_at=end,
        sampling_rate_hz=1.0,
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
