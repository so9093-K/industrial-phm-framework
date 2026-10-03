from industrial_phm.apps import operations_app_path


def test_operations_v2_app_delegates_runtime_composition() -> None:
    source = operations_app_path().read_text(encoding="utf-8")

    assert "load_operations_app_context()" in source
    assert "load_operations_app_snapshot()" not in source
    assert "OperationsAppActions(" not in source
    assert "ThreadPoolExecutor" not in source
    assert "asyncio.run(" not in source
    assert "browse_opcua_variables(" not in source

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


def test_operations_v2_app_does_not_reexport_storage_topology_paths() -> None:
    source = operations_app_path().read_text(encoding="utf-8")

    for internal_path_name in (
        "registry_path =",
        "source_runtime_path =",
        "acquisition_telemetry_path =",
        "acquisition_spool_path =",
        "collection_control_path =",
        "field_analysis_path =",
        "phase_analysis_path =",
        "analysis_runtime_path =",
        "window_state_path =",
        "analysis_ledger_path =",
        "finding_path =",
        "review_path =",
        "history_catalog_path =",
        "history_data_path =",
    ):
        assert internal_path_name not in source
