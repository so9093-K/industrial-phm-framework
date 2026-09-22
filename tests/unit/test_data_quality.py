import pytest

from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
    DataQualityState,
)


def test_data_quality_assessment_is_pass_without_issues() -> None:
    assessment = DataQualityAssessment()

    assert assessment.state == DataQualityState.PASS
    assert assessment.issues == ()
    assert assessment.issue_codes == ()


def test_data_quality_assessment_uses_strongest_recorded_severity() -> None:
    warning = DataQualityIssue(
        code="irregular-sampling",
        severity=DataQualitySeverity.WARNING,
        message="sampling interval varies",
    )
    error = DataQualityIssue(
        code="missing-values",
        severity=DataQualitySeverity.ERROR,
        message="source contains missing values",
    )

    assessment = DataQualityAssessment([warning, error])

    assert assessment.state == DataQualityState.ERROR
    assert assessment.issues == (warning, error)
    assert assessment.issue_codes == ("irregular-sampling", "missing-values")


def test_data_quality_assessment_rejects_non_issue_values() -> None:
    with pytest.raises(ValueError, match="DataQualityIssue"):
        DataQualityAssessment([object()])  # type: ignore[list-item]
