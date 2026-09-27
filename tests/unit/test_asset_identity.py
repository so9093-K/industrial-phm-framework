from datetime import UTC, datetime

import pytest

from industrial_phm.application import (
    AnalysisRun,
    AssetIdentity,
    AssetObservationSummary,
    ChannelIdentity,
    ComponentIdentity,
    FileSourceConfig,
    MeasurementPointIdentity,
    OperationalFinding,
    RegisteredSource,
)
from industrial_phm.contracts import DataQualityAssessment


def test_asset_identity_contract_preserves_explicit_hierarchy_without_inference() -> None:
    asset = AssetIdentity("pump-01")
    component = ComponentIdentity(asset_id="pump-01", component_id="drive-end-bearing")
    point = MeasurementPointIdentity(
        asset_id="pump-01",
        component_id="drive-end-bearing",
        measurement_point_id="de-vibration",
    )
    channel = ChannelIdentity(
        asset_id="pump-01",
        component_id="drive-end-bearing",
        measurement_point_id="de-vibration",
        channel_id="vibration_x",
    )

    assert component.asset == asset
    assert point.asset == asset
    assert point.component == component
    assert channel.asset == asset
    assert channel.component == component
    assert channel.measurement_point == point


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: AssetIdentity(""), "asset_id"),
        (
            lambda: ComponentIdentity(asset_id="pump-01", component_id=" component "),
            "component_id",
        ),
        (
            lambda: MeasurementPointIdentity(
                asset_id="pump-01",
                measurement_point_id=" ",
            ),
            "measurement_point_id",
        ),
        (
            lambda: ChannelIdentity(
                asset_id="pump-01",
                channel_id=" vibration ",
            ),
            "channel_id",
        ),
    ],
)
def test_asset_identity_contract_rejects_ambiguous_identifier_whitespace(
    factory,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


def test_registered_source_projects_asset_measurement_point_and_channels() -> None:
    source = RegisteredSource(
        source_id="field:pump-01",
        name="Pump 01 CSV",
        config=FileSourceConfig(
            source_path="data/pump.csv",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_columns=("vibration_x", "temperature"),
            sampling_rate_hz=1_000.0,
        ),
        registered_at=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
    )

    assert source.asset_identity == AssetIdentity("pump-01")
    assert source.measurement_point_identity == MeasurementPointIdentity(
        asset_id="pump-01",
        measurement_point_id="drive-end",
    )
    assert source.channel_identities == (
        ChannelIdentity(
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_id="vibration_x",
        ),
        ChannelIdentity(
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_id="temperature",
        ),
    )


def test_operational_records_share_one_first_class_asset_scope() -> None:
    observed_at = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    observation = AssetObservationSummary(
        asset_id="pump-01",
        source_id="field:pump-01",
        measurement_point_id="drive-end",
        channels=("vibration_x",),
        sample_count=1,
        observed_start_at=observed_at,
        observed_end_at=observed_at,
        data_quality=DataQualityAssessment(),
    )
    run = AnalysisRun(
        analysis_run_id="analysis-1",
        asset_id="pump-01",
        source_id="field:pump-01",
        measurement_point_id="drive-end",
        observed_start_at=observed_at,
        observed_end_at=observed_at,
        started_at=observed_at,
        completed_at=observed_at,
        data_quality=DataQualityAssessment(),
        capability_ids=("field-vibration-statistical-features-v1",),
    )
    finding = OperationalFinding(
        finding_id="finding-1",
        analysis_run_id="analysis-1",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        observed_at=observed_at,
        capability_id="field-vibration-statistical-features-v1",
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=("evidence-1",),
    )

    expected_asset = AssetIdentity("pump-01")
    expected_point = MeasurementPointIdentity(
        asset_id="pump-01",
        measurement_point_id="drive-end",
    )

    assert observation.asset_identity == expected_asset
    assert run.asset_identity == expected_asset
    assert finding.asset_identity == expected_asset
    assert observation.measurement_point_identity == expected_point
    assert run.measurement_point_identity == expected_point
    assert finding.measurement_point_identity == expected_point
    assert observation.channel_identities == (
        ChannelIdentity(
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_id="vibration_x",
        ),
    )
