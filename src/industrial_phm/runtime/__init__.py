"""Continuous-runtime infrastructure adapters."""

from industrial_phm.runtime.acquisition_spool import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
)
from industrial_phm.runtime.acquisition_telemetry import (
    AcquisitionTelemetryFormatError,
    SqliteAcquisitionTelemetryRepository,
)
from industrial_phm.runtime.collection_control import (
    CollectionControlFormatError,
    SqliteCollectionControlRepository,
)
from industrial_phm.runtime.collection_service import (
    CollectionServicePolicy,
    CollectionServiceResult,
    run_collection_service,
)
from industrial_phm.runtime.history_writer import (
    run_spool_to_history_writer,
    write_next_spool_batch,
)
from industrial_phm.runtime.opcua_acquisition import (
    OpcUaSessionLostError,
    OpcUaSubscriptionOverflowError,
    OpcUaUnpersistedNotificationError,
    run_registered_opcua_acquisition_worker,
)
from industrial_phm.runtime.operations_config import (
    OPERATIONS_CONFIG_SCHEMA,
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsConfigFormatError,
    OperationsRuntimeConfig,
    load_operations_runtime_config,
)
from industrial_phm.runtime.operations_runtime import (
    OperationsComponentKind,
    OperationsComponentLaunch,
    OperationsRuntimePlan,
    build_operations_runtime_plan,
)
from industrial_phm.runtime.operations_status import (
    DEFAULT_RUNTIME_HEARTBEAT_TIMEOUT,
    OperationsComponentStatus,
    OperationsProcessEvidence,
    OperationsRuntimeCondition,
    OperationsRuntimeStatus,
    OperationsSupervisorStatus,
    build_operations_runtime_status,
    inspect_operations_runtime_status,
)
from industrial_phm.runtime.operations_supervisor import (
    OperationsChildProcessState,
    OperationsSupervisorResult,
    OperationsSupervisorState,
    OperationsSupervisorStateKind,
    OperationsSupervisorStateRepository,
    run_operations_supervisor,
)
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    OperationsWorkspaceInitialization,
    initialize_operations_workspace,
)
from industrial_phm.runtime.window_coordinator import (
    rebuild_registered_opcua_observation_windows,
    run_continuous_registered_opcua_observation_windows,
)

__all__ = [
    "DEFAULT_RUNTIME_HEARTBEAT_TIMEOUT",
    "OPERATIONS_CONFIG_SCHEMA",
    "AcquisitionTelemetryFormatError",
    "CollectionControlFormatError",
    "CollectionServicePolicy",
    "CollectionServiceResult",
    "OpcUaSessionLostError",
    "OpcUaSubscriptionOverflowError",
    "OpcUaUnpersistedNotificationError",
    "OperationsAnalysisConfig",
    "OperationsChildProcessState",
    "OperationsCollectionConfig",
    "OperationsComponentKind",
    "OperationsComponentLaunch",
    "OperationsComponentStatus",
    "OperationsConfigFormatError",
    "OperationsProcessEvidence",
    "OperationsRuntimeCondition",
    "OperationsRuntimeConfig",
    "OperationsRuntimePlan",
    "OperationsRuntimeStatus",
    "OperationsSupervisorResult",
    "OperationsSupervisorState",
    "OperationsSupervisorStateKind",
    "OperationsSupervisorStateRepository",
    "OperationsSupervisorStatus",
    "OperationsWorkspace",
    "OperationsWorkspaceInitialization",
    "SqliteAcquisitionSpool",
    "SqliteAcquisitionSpoolConfig",
    "SqliteAcquisitionTelemetryRepository",
    "SqliteCollectionControlRepository",
    "build_operations_runtime_plan",
    "build_operations_runtime_status",
    "initialize_operations_workspace",
    "inspect_operations_runtime_status",
    "load_operations_runtime_config",
    "rebuild_registered_opcua_observation_windows",
    "run_collection_service",
    "run_continuous_registered_opcua_observation_windows",
    "run_operations_supervisor",
    "run_registered_opcua_acquisition_worker",
    "run_spool_to_history_writer",
    "write_next_spool_batch",
]
