"""Small domain-neutral data-quality vocabulary used at source boundaries."""

from __future__ import annotations

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
