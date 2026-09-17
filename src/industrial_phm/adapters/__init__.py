"""Domain adapter boundary."""

from industrial_phm.adapters.base import DomainAdapter
from industrial_phm.adapters.ims import (
    ImsBearingAdapter,
    ImsBearingSourceError,
    ImsBearingTestSummary,
    ImsBearingValidationReport,
    validate_ims_source,
)
from industrial_phm.adapters.xjtu import (
    XjtuSyAdapter,
    XjtuSySourceError,
    XjtuSyValidationReport,
    validate_xjtu_source,
)

__all__ = [
    "DomainAdapter",
    "ImsBearingAdapter",
    "ImsBearingSourceError",
    "ImsBearingTestSummary",
    "ImsBearingValidationReport",
    "XjtuSyAdapter",
    "XjtuSySourceError",
    "XjtuSyValidationReport",
    "validate_ims_source",
    "validate_xjtu_source",
]
