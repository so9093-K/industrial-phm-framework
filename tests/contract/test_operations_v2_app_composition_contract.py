from industrial_phm.apps import operations_app_path


def test_operations_v2_app_delegates_read_repository_composition() -> None:
    source = operations_app_path().read_text(encoding="utf-8")

    assert "load_operations_app_snapshot()" in source
    for forbidden in (
        "DuckLakeAssetHistory(",
        "SqliteAcquisitionTelemetryRepository(",
        "SqliteAcquisitionSpool(",
        "SqliteObservationWindowRepository(",
        "SqlitePhaseUnbalanceRepository(",
        "SqliteWindowAnalysisLedger(",
        "JsonWindowAnalysisRuntimeRepository(",
        "JsonSourceRepository(",
        "JsonSourceRuntimeRepository(",
        "SqliteCollectionControlRepository(",
        "JsonFieldFeatureAnalysisRepository(",
        "JsonOperationalFindingRepository(",
        "JsonFindingReviewRepository(",
    ):
        assert forbidden not in source
