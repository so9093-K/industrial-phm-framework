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
    MIMII_EVALUATION_TEST_SECTIONS,
    MimiiDueAdapter,
    MimiiDueEvaluationTestClip,
    MimiiDueEvaluationTestReport,
    MimiiDueSourceError,
    MimiiDueValidationReport,
    iter_mimii_evaluation_test_clips,
    read_mimii_evaluation_test_series,
    validate_mimii_due_source,
    validate_mimii_evaluation_test_source,
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
    "MIMII_DUE_CHANNELS",
    "MIMII_EVALUATION_TEST_SECTIONS",
    "XJTU_SY_CHANNELS",
    "DomainAdapter",
    "ImsBearingAdapter",
    "ImsBearingSourceError",
    "ImsBearingTestSummary",
    "ImsBearingValidationReport",
    "MimiiDueAdapter",
    "MimiiDueEvaluationTestClip",
    "MimiiDueEvaluationTestReport",
    "MimiiDueSourceError",
    "MimiiDueValidationReport",
    "XjtuSyAdapter",
    "XjtuSySourceError",
    "XjtuSyValidationReport",
    "get_xjtu_expected_acquisition_count",
    "iter_mimii_evaluation_test_clips",
    "read_mimii_evaluation_test_series",
    "validate_ims_source",
    "validate_mimii_due_source",
    "validate_mimii_evaluation_test_source",
    "validate_xjtu_source",
]
