"""Domain adapter boundary."""

from industrial_phm.adapters.base import DomainAdapter
from industrial_phm.adapters.xjtu import (
    XjtuSyAdapter,
    XjtuSySourceError,
    XjtuSyValidationReport,
    validate_xjtu_source,
)

__all__ = [
    "DomainAdapter",
    "XjtuSyAdapter",
    "XjtuSySourceError",
    "XjtuSyValidationReport",
    "validate_xjtu_source",
]
