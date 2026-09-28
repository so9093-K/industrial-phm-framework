"""Continuous-runtime infrastructure adapters."""

from industrial_phm.runtime.acquisition_spool import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
)
from industrial_phm.runtime.history_writer import (
    run_spool_to_history_writer,
    write_next_spool_batch,
)
from industrial_phm.runtime.opcua_acquisition import (
    run_registered_opcua_acquisition_worker,
)

__all__ = [
    "SqliteAcquisitionSpool",
    "SqliteAcquisitionSpoolConfig",
    "run_registered_opcua_acquisition_worker",
    "run_spool_to_history_writer",
    "write_next_spool_batch",
]
