"""Architecture contracts for the packaged Operations app boundary."""

import ast

from industrial_phm.apps import operations_app_path


def _operations_tree() -> ast.Module:
    return ast.parse(operations_app_path().read_text(encoding="utf-8"))


def _imports(tree: ast.AST) -> tuple[set[str], set[tuple[str, str]]]:
    modules: set[str] = set()
    symbols: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            symbols.update((module, alias.name) for alias in node.names)
    return modules, symbols


def test_operations_app_delegates_runtime_composition() -> None:
    modules, symbols = _imports(_operations_tree())

    assert (
        "industrial_phm.runtime.operations_app_context",
        "load_operations_app_context",
    ) in symbols

    forbidden_modules = {
        "asyncio",
        "concurrent.futures",
        "industrial_phm.history",
    }
    assert modules.isdisjoint(forbidden_modules)

    forbidden_symbols = {
        "DuckLakeAssetHistory",
        "SqliteAcquisitionTelemetryRepository",
        "SqliteAcquisitionSpool",
        "SqliteObservationWindowRepository",
        "SqlitePhaseUnbalanceRepository",
        "SqliteWindowAnalysisLedger",
        "JsonWindowAnalysisRuntimeRepository",
        "JsonSourceRepository",
        "JsonSourceRuntimeRepository",
        "SqliteCollectionControlRepository",
        "JsonFieldFeatureAnalysisRepository",
        "JsonOperationalFindingRepository",
        "JsonFindingReviewRepository",
        "ThreadPoolExecutor",
        "browse_opcua_variables",
        "load_operations_app_snapshot",
        "OperationsAppActions",
    }
    imported_names = {name for _, name in symbols}
    assert imported_names.isdisjoint(forbidden_symbols)


def test_operations_app_does_not_own_storage_topology_aliases() -> None:
    tree = _operations_tree()
    assigned_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    internal_path_names = {
        "registry_path",
        "source_runtime_path",
        "acquisition_telemetry_path",
        "acquisition_spool_path",
        "collection_control_path",
        "field_analysis_path",
        "phase_analysis_path",
        "analysis_runtime_path",
        "window_state_path",
        "analysis_ledger_path",
        "finding_path",
        "review_path",
        "history_catalog_path",
        "history_data_path",
    }
    assert assigned_names.isdisjoint(internal_path_names)
