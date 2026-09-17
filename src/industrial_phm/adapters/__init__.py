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
    XJTU_SY_CHANNELS,
    XjtuSyAdapter,
    XjtuSySourceError,
    XjtuSyValidationReport,
    validate_xjtu_source,
)

__all__ = [
    "XJTU_SY_CHANNELS",
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
