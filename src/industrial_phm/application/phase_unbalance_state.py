"""Durable local history of three-phase unbalance analysis results."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.asset_history import HistoricalInputReference
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.phase_unbalance import (
    ChannelSelection,
    PhaseUnbalanceAnalysis,
    PhaseUnbalanceConfig,
    PhaseUnbalanceEvidence,
    UnbalanceBucket,
    UnbalanceQuantity,
    UnbalanceSeriesResult,
)
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)

_SCHEMA = "industrial-phm-phase-unbalance-v1"


class PhaseUnbalanceHistoryFormatError(ValueError):
    """Raised when persisted unbalance history is invalid."""


class JsonPhaseUnbalanceRepository:
    """Append-only-by-run local repository; a replay must be identical."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def list_results(self) -> tuple[PhaseUnbalanceAnalysis, ...]:
        if not self._path.exists():
            return ()
        try:
            root = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(root, dict) or root.get("schema") != _SCHEMA:
                raise PhaseUnbalanceHistoryFormatError(
                    f"unsupported phase unbalance history schema in {self._path}"
                )
            results = tuple(_parse(item) for item in root["results"])
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, PhaseUnbalanceHistoryFormatError):
                raise
            raise PhaseUnbalanceHistoryFormatError(
                f"invalid phase unbalance history: {error}"
            ) from error
        run_ids = [r.run.analysis_run_id for r in results]
        if len(set(run_ids)) != len(run_ids):
            raise PhaseUnbalanceHistoryFormatError("duplicate analysis_run_id in history")
        return results

    def record(self, result: PhaseUnbalanceAnalysis) -> None:
        if not isinstance(result, PhaseUnbalanceAnalysis):
            raise ValueError("result must be PhaseUnbalanceAnalysis")
        results = {r.run.analysis_run_id: r for r in self.list_results()}
        existing = results.get(result.run.analysis_run_id)
        if existing is not None:
            if existing != result:
                raise ValueError("analysis_run_id already exists with different evidence")
            return
        if any(r.evidence.evidence_id == result.evidence.evidence_id for r in results.values()):
            raise ValueError("evidence_id already exists for a different analysis run")
        results[result.run.analysis_run_id] = result
        ordered = sorted(
            results.values(), key=lambda r: (r.run.completed_at, r.run.analysis_run_id)
        )
        payload = {"schema": _SCHEMA, "results": [_serialize(r) for r in ordered]}
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(handle.name, self._path)
        finally:
            Path(handle.name).unlink(missing_ok=True)


def _time(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _serialize(result: PhaseUnbalanceAnalysis) -> dict[str, object]:
    run, evidence = result.run, result.evidence
    reference = evidence.input_reference
    config = evidence.config
    return {
        "run": {
            "analysis_run_id": run.analysis_run_id,
            "asset_id": run.asset_id,
            "source_id": run.source_id,
            "measurement_point_id": run.measurement_point_id,
            "observed_start_at": _time(run.observed_start_at),
            "observed_end_at": _time(run.observed_end_at),
            "started_at": _time(run.started_at),
            "completed_at": _time(run.completed_at),
            "capability_ids": list(run.capability_ids),
            "data_quality": [
                {"code": i.code, "severity": i.severity.value, "message": i.message}
                for i in run.data_quality.issues
            ],
        },
        "evidence": {
            "evidence_id": evidence.evidence_id,
            "analysis_run_id": evidence.analysis_run_id,
            "capability_id": evidence.capability_id,
            "algorithm_version": evidence.algorithm_version,
            "interpretation": evidence.interpretation,
            "source_id": evidence.source_id,
            "semantic_versions": list(evidence.semantic_versions),
            "input_reference": {
                "snapshot_id": reference.snapshot_id,
                "asset_id": reference.asset_id,
                "start_at": _time(reference.start_at),
                "end_at": _time(reference.end_at),
                "measurement_point_id": reference.measurement_point_id,
                "channel_ids": list(reference.channel_ids),
            },
            "config": {
                "voltage_channels": _optional_list(config.voltage_channels),
                "current_channels": _optional_list(config.current_channels),
                "min_mean_voltage_v": config.min_mean_voltage_v,
                "min_mean_current_a": config.min_mean_current_a,
                "bucket_count": config.bucket_count,
            },
            "results": [
                {
                    "quantity": r.quantity.value,
                    "evaluated_samples": r.evaluated_samples,
                    "excluded_samples": dict(r.excluded_samples),
                    "median_percent": r.median_percent,
                    "p95_percent": r.p95_percent,
                    "max_percent": r.max_percent,
                    "max_at": _time(r.max_at),
                    "buckets": [
                        [
                            _time(b.start_at),
                            _time(b.end_at),
                            b.sample_count,
                            b.median_percent,
                            b.max_percent,
                        ]
                        for b in r.buckets
                    ],
                    "channels": list(r.channels),
                    "channel_selection": r.channel_selection.value,
                }
                for r in evidence.results
            ],
        },
    }


def _optional_list(value: tuple[str, ...] | None) -> list[str] | None:
    return None if value is None else list(value)


def _optional_triple(value: Any) -> tuple[str, str, str] | None:
    if value is None:
        return None
    first, second, third = value
    return (first, second, third)


def _dt(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _parse(raw: Mapping[str, Any]) -> PhaseUnbalanceAnalysis:
    run_raw, ev = raw["run"], raw["evidence"]
    run = AnalysisRun(
        analysis_run_id=run_raw["analysis_run_id"],
        asset_id=run_raw["asset_id"],
        source_id=run_raw["source_id"],
        measurement_point_id=run_raw["measurement_point_id"],
        observed_start_at=_dt(run_raw["observed_start_at"]),
        observed_end_at=_dt(run_raw["observed_end_at"]),
        started_at=_dt(run_raw["started_at"]),
        completed_at=_dt(run_raw["completed_at"]),
        capability_ids=tuple(run_raw["capability_ids"]),
        data_quality=DataQualityAssessment(
            tuple(
                DataQualityIssue(i["code"], DataQualitySeverity(i["severity"]), i["message"])
                for i in run_raw["data_quality"]
            )
        ),
    )
    ref, cfg = ev["input_reference"], ev["config"]
    evidence = PhaseUnbalanceEvidence(
        evidence_id=ev["evidence_id"],
        analysis_run_id=ev["analysis_run_id"],
        capability_id=ev["capability_id"],
        algorithm_version=ev["algorithm_version"],
        interpretation=ev["interpretation"],
        source_id=ev["source_id"],
        semantic_versions=tuple(ev["semantic_versions"]),
        input_reference=HistoricalInputReference(
            snapshot_id=ref["snapshot_id"],
            asset_id=ref["asset_id"],
            start_at=_dt(ref["start_at"]),
            end_at=_dt(ref["end_at"]),
            measurement_point_id=ref["measurement_point_id"],
            channel_ids=tuple(ref["channel_ids"]),
        ),
        config=PhaseUnbalanceConfig(
            voltage_channels=_optional_triple(cfg["voltage_channels"]),
            current_channels=_optional_triple(cfg["current_channels"]),
            min_mean_voltage_v=cfg["min_mean_voltage_v"],
            min_mean_current_a=cfg["min_mean_current_a"],
            bucket_count=cfg["bucket_count"],
        ),
        results=tuple(
            UnbalanceSeriesResult(
                quantity=UnbalanceQuantity(r["quantity"]),
                evaluated_samples=r["evaluated_samples"],
                excluded_samples=dict(r["excluded_samples"]),
                median_percent=r["median_percent"],
                p95_percent=r["p95_percent"],
                max_percent=r["max_percent"],
                max_at=None if r["max_at"] is None else _dt(r["max_at"]),
                buckets=tuple(
                    UnbalanceBucket(_dt(b[0]), _dt(b[1]), b[2], b[3], b[4]) for b in r["buckets"]
                ),
                # Records written before role resolution named channels explicitly.
                channels=tuple(
                    r["channels"]
                    if "channels" in r
                    else cfg[
                        "voltage_channels" if r["quantity"] == "voltage" else "current_channels"
                    ]
                ),
                channel_selection=ChannelSelection(r.get("channel_selection", "explicit")),
            )
            for r in ev["results"]
        ),
    )
    return PhaseUnbalanceAnalysis(run, evidence)
