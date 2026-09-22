"""Domain adapter boundary."""

from industrial_phm.adapters.base import DomainAdapter
from industrial_phm.adapters.csv_sensor import (
    CsvSensorAdapter,
    CsvSensorLayout,
    CsvSensorSourceError,
    CsvSensorValidationReport,
    validate_csv_sensor_source,
)
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
    "CsvSensorAdapter",
    "CsvSensorLayout",
    "CsvSensorSourceError",
    "CsvSensorValidationReport",
    "DomainAdapter",
    "ImsBearingAdapter",
    "ImsBearingSourceError",
    "ImsBearingTestSummary",
    "ImsBearingValidationReport",
    "MIMII_DUE_CHANNELS",
    "MIMII_EVALUATION_TEST_SECTIONS",
    "MimiiDueAdapter",
    "MimiiDueEvaluationTestClip",
    "MimiiDueEvaluationTestReport",
    "MimiiDueSourceError",
    "MimiiDueValidationReport",
    "XJTU_SY_CHANNELS",
    "XjtuSyAdapter",
    "XjtuSySourceError",
    "XjtuSyValidationReport",
    "get_xjtu_expected_acquisition_count",
    "iter_mimii_evaluation_test_clips",
    "read_mimii_evaluation_test_series",
    "validate_csv_sensor_source",
    "validate_ims_source",
    "validate_mimii_due_source",
    "validate_mimii_evaluation_test_source",
    "validate_xjtu_source",
]
