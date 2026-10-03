"""Durable local history for operational FILE feature-analysis results."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from industrial_phm.application.file_feature_analysis import (
    OperationalVibrationFeatureEvidence,
    RegisteredFileFeatureAnalysis,
)
from industrial_phm.application.observation import SourceSnapshotEvidence
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)

# Historical schema identity is required to read existing workspace evidence.
_FILE_FEATURE_ANALYSIS_SCHEMA_V1 = "industrial-phm-field-feature-analysis-v1"
_ROOT_KEYS = frozenset({"schema", "results"})
_RESULT_KEYS = frozenset({"run", "evidence"})
_RUN_KEYS = frozenset(
    {
        "analysis_run_id",
        "asset_id",
        "source_id",
        "measurement_point_id",
        "observed_start_at",
        "observed_end_at",
        "started_at",
        "completed_at",
        "data_quality",
        "model_deployment_id",
        "source_snapshots",
        "capability_ids",
    }
)
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_id",
        "analysis_run_id",
        "capability_id",
        "feature_set_id",
        "feature_names",
        "values",
        "source_snapshot_sha256",
    }
)
_QUALITY_KEYS = frozenset({"issues"})
_ISSUE_KEYS = frozenset({"code", "severity", "message"})
_SNAPSHOT_KEYS = frozenset({"name", "sha256", "size_bytes"})


class FileFeatureAnalysisHistoryFormatError(ValueError):
    """Raised when persisted operational FILE feature-analysis history is invalid."""


class JsonFileFeatureAnalysisRepository:
    """Append-only-by-run local repository for operational feature-analysis results."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured history path."""
        return self._path

    def list_results(self) -> tuple[RegisteredFileFeatureAnalysis, ...]:
        """Return results ordered by completion time and run identity."""
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"FILE feature analysis history path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise FileFeatureAnalysisHistoryFormatError(
                "FILE feature analysis history must contain valid JSON"
            ) from error

        root = _require_mapping(raw, "FILE feature analysis history root")
        _require_exact_keys(root, _ROOT_KEYS, "FILE feature analysis history root")
        schema = _require_string(root["schema"], "FILE feature analysis history schema")
        if schema != _FILE_FEATURE_ANALYSIS_SCHEMA_V1:
            raise FileFeatureAnalysisHistoryFormatError(
                f"unsupported FILE feature analysis history schema: {schema!r}"
            )

        results_raw = root["results"]
        if not isinstance(results_raw, list):
            raise FileFeatureAnalysisHistoryFormatError(
                "FILE feature analysis history results must be a JSON array"
            )
        results = tuple(
            _parse_result(value, index=index) for index, value in enumerate(results_raw)
        )
        run_ids = tuple(result.run.analysis_run_id for result in results)
        evidence_ids = tuple(result.evidence.evidence_id for result in results)
        if len(set(run_ids)) != len(run_ids):
            raise FileFeatureAnalysisHistoryFormatError(
                "FILE feature analysis history contains duplicate analysis_run_id values"
            )
        if len(set(evidence_ids)) != len(evidence_ids):
            raise FileFeatureAnalysisHistoryFormatError(
                "FILE feature analysis history contains duplicate evidence_id values"
            )
        return tuple(
            sorted(
                results,
                key=lambda result: (
                    result.run.completed_at,
                    result.run.analysis_run_id,
                ),
            )
        )

    def record(self, result: RegisteredFileFeatureAnalysis) -> None:
        """Append one new result or accept an exact idempotent replay."""
        if not isinstance(result, RegisteredFileFeatureAnalysis):
            raise ValueError("result must be RegisteredFileFeatureAnalysis")

        results = {item.run.analysis_run_id: item for item in self.list_results()}
        current = results.get(result.run.analysis_run_id)
        if current is not None:
            if current != result:
                raise ValueError("analysis_run_id already exists with different persisted evidence")
            return

        if any(
            item.evidence.evidence_id == result.evidence.evidence_id for item in results.values()
        ):
            raise ValueError("evidence_id already exists for a different analysis run")

        results[result.run.analysis_run_id] = result
        self._write(tuple(results.values()))

    def _write(self, results: Sequence[RegisteredFileFeatureAnalysis]) -> None:
        ordered = tuple(
            sorted(
                results,
                key=lambda result: (
                    result.run.completed_at,
                    result.run.analysis_run_id,
                ),
            )
        )
        payload = {
            "schema": _FILE_FEATURE_ANALYSIS_SCHEMA_V1,
            "results": [_serialize_result(result) for result in ordered],
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


def _serialize_result(result: RegisteredFileFeatureAnalysis) -> dict[str, object]:
    run = result.run
    evidence = result.evidence
    return {
        "run": {
            "analysis_run_id": run.analysis_run_id,
            "asset_id": run.asset_id,
            "source_id": run.source_id,
            "measurement_point_id": run.measurement_point_id,
            "observed_start_at": run.observed_start_at.isoformat(),
            "observed_end_at": run.observed_end_at.isoformat(),
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat(),
            "data_quality": {
                "issues": [
                    {
                        "code": issue.code,
                        "severity": issue.severity.value,
                        "message": issue.message,
                    }
                    for issue in run.data_quality.issues
                ]
            },
            "model_deployment_id": run.model_deployment_id,
            "source_snapshots": [
                {
                    "name": snapshot.name,
                    "sha256": snapshot.sha256,
                    "size_bytes": snapshot.size_bytes,
                }
                for snapshot in run.source_snapshots
            ],
            "capability_ids": list(run.capability_ids),
        },
        "evidence": {
            "evidence_id": evidence.evidence_id,
            "analysis_run_id": evidence.analysis_run_id,
            "capability_id": evidence.capability_id,
            "feature_set_id": evidence.feature_set_id,
            "feature_names": list(evidence.feature_names),
            "values": list(evidence.values),
            "source_snapshot_sha256": evidence.source_snapshot_sha256,
        },
    }


def _parse_result(value: object, *, index: int) -> RegisteredFileFeatureAnalysis:
    label = f"field analysis results[{index}]"
    raw = _require_mapping(value, label)
    _require_exact_keys(raw, _RESULT_KEYS, label)

    run_raw = _require_mapping(raw["run"], f"{label}.run")
    _require_exact_keys(run_raw, _RUN_KEYS, f"{label}.run")
    evidence_raw = _require_mapping(raw["evidence"], f"{label}.evidence")
    _require_exact_keys(evidence_raw, _EVIDENCE_KEYS, f"{label}.evidence")

    quality_raw = _require_mapping(run_raw["data_quality"], f"{label}.run.data_quality")
    _require_exact_keys(quality_raw, _QUALITY_KEYS, f"{label}.run.data_quality")
    issues_raw = quality_raw["issues"]
    if not isinstance(issues_raw, list):
        raise FileFeatureAnalysisHistoryFormatError(
            f"{label}.run.data_quality.issues must be a JSON array"
        )
    issues = tuple(
        _parse_issue(issue, label=f"{label}.run.data_quality.issues[{issue_index}]")
        for issue_index, issue in enumerate(issues_raw)
    )

    snapshots_raw = run_raw["source_snapshots"]
    if not isinstance(snapshots_raw, list):
        raise FileFeatureAnalysisHistoryFormatError(f"{label}.run.source_snapshots must be a JSON array")
    snapshots = tuple(
        _parse_snapshot(
            snapshot,
            label=f"{label}.run.source_snapshots[{snapshot_index}]",
        )
        for snapshot_index, snapshot in enumerate(snapshots_raw)
    )

    run = AnalysisRun(
        analysis_run_id=_require_string(run_raw["analysis_run_id"], f"{label}.run.analysis_run_id"),
        asset_id=_require_string(run_raw["asset_id"], f"{label}.run.asset_id"),
        source_id=_require_string(run_raw["source_id"], f"{label}.run.source_id"),
        measurement_point_id=_require_optional_string(
            run_raw["measurement_point_id"],
            f"{label}.run.measurement_point_id",
        ),
        observed_start_at=_require_datetime(
            run_raw["observed_start_at"], f"{label}.run.observed_start_at"
        ),
        observed_end_at=_require_datetime(
            run_raw["observed_end_at"], f"{label}.run.observed_end_at"
        ),
        started_at=_require_datetime(run_raw["started_at"], f"{label}.run.started_at"),
        completed_at=_require_datetime(run_raw["completed_at"], f"{label}.run.completed_at"),
        data_quality=DataQualityAssessment(issues),
        model_deployment_id=_require_optional_string(
            run_raw["model_deployment_id"],
            f"{label}.run.model_deployment_id",
        ),
        source_snapshots=snapshots,
        capability_ids=_require_string_list(
            run_raw["capability_ids"], f"{label}.run.capability_ids"
        ),
    )
    evidence = OperationalVibrationFeatureEvidence(
        evidence_id=_require_string(evidence_raw["evidence_id"], f"{label}.evidence.evidence_id"),
        analysis_run_id=_require_string(
            evidence_raw["analysis_run_id"], f"{label}.evidence.analysis_run_id"
        ),
        capability_id=_require_string(
            evidence_raw["capability_id"], f"{label}.evidence.capability_id"
        ),
        feature_set_id=_require_string(
            evidence_raw["feature_set_id"], f"{label}.evidence.feature_set_id"
        ),
        feature_names=_require_string_list(
            evidence_raw["feature_names"], f"{label}.evidence.feature_names"
        ),
        values=_require_number_list(evidence_raw["values"], f"{label}.evidence.values"),
        source_snapshot_sha256=_require_string(
            evidence_raw["source_snapshot_sha256"],
            f"{label}.evidence.source_snapshot_sha256",
        ),
    )
    try:
        return RegisteredFileFeatureAnalysis(run=run, evidence=evidence)
    except ValueError as error:
        raise FileFeatureAnalysisHistoryFormatError(f"{label} is invalid: {error}") from error


def _parse_issue(value: object, *, label: str) -> DataQualityIssue:
    raw = _require_mapping(value, label)
    _require_exact_keys(raw, _ISSUE_KEYS, label)
    try:
        severity = DataQualitySeverity(_require_string(raw["severity"], f"{label}.severity"))
        return DataQualityIssue(
            code=_require_string(raw["code"], f"{label}.code"),
            severity=severity,
            message=_require_string(raw["message"], f"{label}.message"),
        )
    except ValueError as error:
        raise FileFeatureAnalysisHistoryFormatError(f"{label} is invalid: {error}") from error


def _parse_snapshot(value: object, *, label: str) -> SourceSnapshotEvidence:
    raw = _require_mapping(value, label)
    _require_exact_keys(raw, _SNAPSHOT_KEYS, label)
    try:
        return SourceSnapshotEvidence(
            name=_require_string(raw["name"], f"{label}.name"),
            sha256=_require_string(raw["sha256"], f"{label}.sha256"),
            size_bytes=_require_integer(raw["size_bytes"], f"{label}.size_bytes"),
        )
    except ValueError as error:
        raise FileFeatureAnalysisHistoryFormatError(f"{label} is invalid: {error}") from error


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be a JSON object")
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
        raise FileFeatureAnalysisHistoryFormatError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be a string")
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
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be an ISO 8601 datetime") from error
    if result.utcoffset() is None:
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be timezone-aware")
    return result


def _require_string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be a JSON string array")
    return tuple(value)


def _require_number_list(value: object, label: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be a JSON number array")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise FileFeatureAnalysisHistoryFormatError(f"{label} must contain only JSON numbers")
        numbers.append(float(item))
    return tuple(numbers)


def _require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FileFeatureAnalysisHistoryFormatError(f"{label} must be an integer")
    return value
