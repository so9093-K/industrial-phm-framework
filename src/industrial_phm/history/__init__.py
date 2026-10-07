"""Historical storage adapters."""

from industrial_phm.history.ducklake import (
    DuckLakeAssetHistory,
    DuckLakeAssetHistoryConfig,
    DuckLakeCompactedTable,
    DuckLakeCompactionResult,
    DuckLakeInlinedDataFlush,
    DuckLakeRetentionResult,
    DuckLakeRuntimeFingerprint,
    DuckLakeRuntimeUnavailableError,
    DuckLakeStorageInspection,
)

__all__ = [
    "DuckLakeAssetHistory",
    "DuckLakeAssetHistoryConfig",
    "DuckLakeCompactedTable",
    "DuckLakeCompactionResult",
    "DuckLakeInlinedDataFlush",
    "DuckLakeRetentionResult",
    "DuckLakeRuntimeFingerprint",
    "DuckLakeRuntimeUnavailableError",
    "DuckLakeStorageInspection",
]
