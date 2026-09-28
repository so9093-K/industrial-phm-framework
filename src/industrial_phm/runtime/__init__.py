"""Continuous-runtime infrastructure adapters."""

from industrial_phm.runtime.acquisition_spool import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
)

__all__ = [
    "SqliteAcquisitionSpool",
    "SqliteAcquisitionSpoolConfig",
    "run_registered_opcua_acquisition_worker",
]

from industrial_phm.runtime.opcua_acquisition import (
    run_registered_opcua_acquisition_worker,
)
