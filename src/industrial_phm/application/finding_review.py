"""Manual review findings backed by operational feature evidence."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from industrial_phm.application.field_analysis import RegisteredFieldFeatureAnalysis
from industrial_phm.application.operational import (
    OperationalFinding,
    validate_operational_finding_against_run,
)

HUMAN_REVIEW_FINDING_SEMANTICS_ID = "human-review-request-v1"
HUMAN_REVIEW_FINDING_STATE = "REVIEW_REQUIRED"
_FINDING_SCHEMA_V1 = "industrial-phm-operational-findings-v1"
_ROOT_KEYS = frozenset({"schema", "findings"})
_FINDING_KEYS = frozenset(
    {
        "finding_id",
        "analysis_run_id",
        "asset_id",
        "measurement_point_id",
        "observed_at",
        "capability_id",
        "finding_semantics_id",
        "state",
        "evidence_refs",
    }
)


class OperationalFindingHistoryFormatError(ValueError):
    """Raised when persisted operational finding history is invalid."""


def create_human_review_finding(
    result: RegisteredFieldFeatureAnalysis,
) -> OperationalFinding:
    """Create an explicit human-review request linked to one feature-analysis result.

    The finding is created only because a user requests review. It does not claim that
    the feature values indicate a fault, abnormal condition, health state, or alarm.
    """
    if not isinstance(result, RegisteredFieldFeatureAnalysis):
        raise ValueError("result must be RegisteredFieldFeatureAnalysis")

    finding = OperationalFinding(
        finding_id=f"finding-review-{result.run.analysis_run_id}",
        analysis_run_id=result.run.analysis_run_id,
        asset_id=result.run.asset_id,
        measurement_point_id=result.run.measurement_point_id,
        observed_at=result.run.observed_end_at,
        capability_id=result.evidence.capability_id,
        finding_semantics_id=HUMAN_REVIEW_FINDING_SEMANTICS_ID,
        state=HUMAN_REVIEW_FINDING_STATE,
        evidence_refs=(result.evidence.evidence_id,),
    )
    validate_operational_finding_against_run(finding, result.run)
    return finding


class JsonOperationalFindingRepository:
    """Durable local repository for evidence-linked operational findings."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured finding-history path."""
        return self._path

    def list_findings(self) -> tuple[OperationalFinding, ...]:
        """Return findings ordered by observation time and identity."""
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"operational finding history path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise OperationalFindingHistoryFormatError(
                "operational finding history must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "operational finding history root")
        _require_exact_keys(root, _ROOT_KEYS, "operational finding history root")
        schema = _require_string(root["schema"], "operational finding history schema")
        if schema != _FINDING_SCHEMA_V1:
            raise OperationalFindingHistoryFormatError(
                f"unsupported operational finding history schema: {schema!r}"
            )

        findings_raw = root["findings"]
        if not isinstance(findings_raw, list):
            raise OperationalFindingHistoryFormatError(
                "operational finding history findings must be a JSON array"
            )
        findings = tuple(
            _parse_finding(value, index=index) for index, value in enumerate(findings_raw)
        )
        finding_ids = tuple(finding.finding_id for finding in findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise OperationalFindingHistoryFormatError(
                "operational finding history contains duplicate finding_id values"
            )
        return tuple(
            sorted(
                findings,
                key=lambda finding: (finding.observed_at, finding.finding_id),
            )
        )

    def record(self, finding: OperationalFinding) -> None:
        """Append one finding or accept an exact idempotent replay."""
        if not isinstance(finding, OperationalFinding):
            raise ValueError("finding must be OperationalFinding")

        findings = {item.finding_id: item for item in self.list_findings()}
        current = findings.get(finding.finding_id)
        if current is not None:
            if current != finding:
                raise ValueError("finding_id already exists with different persisted evidence")
            return

        findings[finding.finding_id] = finding
        self._write(tuple(findings.values()))

    def _write(self, findings: Sequence[OperationalFinding]) -> None:
        ordered = tuple(
            sorted(
                findings,
                key=lambda finding: (finding.observed_at, finding.finding_id),
            )
        )
        payload = {
            "schema": _FINDING_SCHEMA_V1,
            "findings": [_serialize_finding(finding) for finding in ordered],
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _serialize_finding(finding: OperationalFinding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "analysis_run_id": finding.analysis_run_id,
        "asset_id": finding.asset_id,
        "measurement_point_id": finding.measurement_point_id,
        "observed_at": finding.observed_at.isoformat(),
        "capability_id": finding.capability_id,
        "finding_semantics_id": finding.finding_semantics_id,
        "state": finding.state,
        "evidence_refs": list(finding.evidence_refs),
    }


def _parse_finding(value: object, *, index: int) -> OperationalFinding:
    label = f"operational findings[{index}]"
    raw = _require_mapping(value, label)
    _require_exact_keys(raw, _FINDING_KEYS, label)
    try:
        return OperationalFinding(
            finding_id=_require_string(raw["finding_id"], f"{label}.finding_id"),
            analysis_run_id=_require_string(raw["analysis_run_id"], f"{label}.analysis_run_id"),
            asset_id=_require_string(raw["asset_id"], f"{label}.asset_id"),
            measurement_point_id=_require_optional_string(
                raw["measurement_point_id"],
                f"{label}.measurement_point_id",
            ),
            observed_at=_require_datetime(raw["observed_at"], f"{label}.observed_at"),
            capability_id=_require_string(raw["capability_id"], f"{label}.capability_id"),
            finding_semantics_id=_require_string(
                raw["finding_semantics_id"],
                f"{label}.finding_semantics_id",
            ),
            state=_require_string(raw["state"], f"{label}.state"),
            evidence_refs=_require_string_list(raw["evidence_refs"], f"{label}.evidence_refs"),
        )
    except ValueError as error:
        if isinstance(error, OperationalFindingHistoryFormatError):
            raise
        raise OperationalFindingHistoryFormatError(f"{label} is invalid: {error}") from error


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise OperationalFindingHistoryFormatError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise OperationalFindingHistoryFormatError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise OperationalFindingHistoryFormatError(f"{label} must be a string")
    return value


def _require_optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, label)


def _require_datetime(value: object, label: str) -> datetime:
    raw = _require_string(value, label)
    try:
        result = datetime.fromisoformat(raw)
    except ValueError as error:
        raise OperationalFindingHistoryFormatError(
            f"{label} must be an ISO 8601 datetime"
        ) from error
    if result.utcoffset() is None:
        raise OperationalFindingHistoryFormatError(f"{label} must be timezone-aware")
    return result


def _require_string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise OperationalFindingHistoryFormatError(f"{label} must be a JSON string array")
    return tuple(value)
