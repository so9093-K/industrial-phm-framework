"""Small domain-neutral data-quality vocabulary used at source boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class DataQualitySeverity(StrEnum):
    """Severity for one observed source-quality issue."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    """One source-quality issue without dataset-specific semantics."""

    code: str
    severity: DataQualitySeverity
    message: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("data quality issue code must not be empty")
        if self.code != self.code.strip():
            raise ValueError("data quality issue code must not contain surrounding whitespace")
        if not self.message.strip():
            raise ValueError("data quality issue message must not be empty")
        if not isinstance(self.severity, DataQualitySeverity):
            raise ValueError("data quality issue severity must be a DataQualitySeverity")


class DataQualityState(StrEnum):
    """Aggregate state derived from recorded quality issues."""

    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DataQualityAssessment:
    """Immutable aggregate assessment without hidden repair or imputation."""

    issues: Sequence[DataQualityIssue] = ()

    def __post_init__(self) -> None:
        issues = tuple(self.issues)
        if any(not isinstance(issue, DataQualityIssue) for issue in issues):
            raise ValueError("issues must contain only DataQualityIssue values")
        object.__setattr__(self, "issues", issues)

    @property
    def state(self) -> DataQualityState:
        """Return the strongest severity represented by the recorded issues."""
        if any(issue.severity == DataQualitySeverity.ERROR for issue in self.issues):
            return DataQualityState.ERROR
        if any(issue.severity == DataQualitySeverity.WARNING for issue in self.issues):
            return DataQualityState.WARNING
        return DataQualityState.PASS

    @property
    def issue_codes(self) -> tuple[str, ...]:
        """Return issue codes in recorded order for presentation and API consumers."""
        return tuple(issue.code for issue in self.issues)
