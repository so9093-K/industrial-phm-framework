"""Domain adapter boundary."""

from industrial_phm.adapters.base import DomainAdapter
from industrial_phm.adapters.ims import (
    ImsBearingAdapter,
    ImsBearingSourceError,
    ImsBearingTestSummary,
    ImsBearingValidationReport,
    validate_ims_source,
)
from industrial_phm.adapters.mimii import (
    MIMII_DUE_CHANNELS,
    MimiiDueAdapter,
    MimiiDueSourceError,
    MimiiDueValidationReport,
    validate_mimii_due_source,
)
from industrial_phm.adapters.xjtu import (
    XJTU_SY_CHANNELS,
    XjtuSyAdapter,
    XjtuSySourceError,
    XjtuSyValidationReport,
    get_xjtu_expected_acquisition_count,
    validate_xjtu_source,
)

__all__ = [
    "XJTU_SY_CHANNELS",
    "DomainAdapter",
    "ImsBearingAdapter",
    "ImsBearingSourceError",
    "ImsBearingTestSummary",
    "ImsBearingValidationReport",
    "MIMII_DUE_CHANNELS",
    "MimiiDueAdapter",
    "MimiiDueSourceError",
    "MimiiDueValidationReport",
    "XjtuSyAdapter",
    "XjtuSySourceError",
    "XjtuSyValidationReport",
    "get_xjtu_expected_acquisition_count",
    "validate_ims_source",
    "validate_mimii_due_source",
    "validate_xjtu_source",
]
