"""Late-binding MIMII DUE external evaluation for sections 03-05.

This evaluator consumes an immutable label-blind score artifact and joins ground-truth
labels at its own edge. It never reads audio, never fits a model, and never rescores a
clip: the scores it evaluates were fixed before any label was available, and the score
artifact digest recorded here proves which scores were used.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from industrial_phm.data import get_dataset
from industrial_phm.experiments.binary_ranking import (
    BinaryRankingEvaluation,
    evaluate_binary_anomaly_ranking,
    harmonic_mean_unit_interval,
)
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_PROTOCOL_ID,
    MIMII_DUE_DATASET_ID,
    MIMII_EXTERNAL_CONFIGURATION_ID,
    MIMII_EXTERNAL_SECTIONS,
    MIMII_EXTERNAL_SPLIT_ID,
    MIMII_MACHINE_TYPES,
)
from industrial_phm.experiments.mimii_external_scoring import (
    MIMII_EXTERNAL_SCORE_SCHEMA_ID,
    MIMII_EXTERNAL_SCORE_SEMANTICS,
)
from industrial_phm.models.output import AnomalyScores

MIMII_EXTERNAL_RESULT_SCHEMA_ID = "mimii-due-domain-shift-external-result-v1"
MIMII_EXTERNAL_EVIDENCE_CLASS = "late-bound-external-evaluation-evidence"
MIMII_EXTERNAL_MAX_FALSE_POSITIVE_RATE = 0.1
MIMII_EXTERNAL_LABEL_MAPPING = {"0": "normal", "1": "anomaly"}
MIMII_EXTERNAL_AVAILABLE_CAPABILITIES = (
    "clip-level-anomaly-scoring",
    "late-bound-external-discrimination-evaluation",
    "source-target-domain-stratified-auc-pauc-evidence",
)
MIMII_EXTERNAL_UNSUPPORTED_CAPABILITIES = (
    "thresholded-state-detection",
    "online-alerting",
    "fault-diagnostics",
    "fault-classification",
    "health-assessment",
    "health-indicator",
    "prognostics-rul",
    "causal-explanation",
    "maintenance-recommendation-priority",
)

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_GROUND_TRUTH_PATTERN = re.compile(
    r"^ground_truth_(?P<machine>[A-Za-z]+)_section_(?P<section>\d{2})_"
    r"(?P<domain>source|target)_test\.csv$"
)


class MimiiExternalEvaluationError(ValueError):
    """Raised when late-binding external evaluation violates its protocol boundary."""


@dataclass(frozen=True, slots=True)
class MimiiExternalStratumEvidence:
    """One machine-type, section and domain external evaluation stratum."""

    machine_type: str
    section: str
    domain: str
    evaluation: BinaryRankingEvaluation


@dataclass(frozen=True, slots=True)
class MimiiExternalAggregate:
    """Harmonic AUC/pAUC summary over a named set of external strata."""

    scope_id: str
    stratum_count: int
    roc_auc_harmonic_mean: float
    partial_roc_auc_harmonic_mean: float


@dataclass(frozen=True, slots=True)
class MimiiExternalEvaluationResult:
    """Late-bound external evidence for the frozen MIMII configuration."""

    code_revision: str
    score_artifact_sha256: str
    score_artifact_code_revision: str
    scored_clip_count: int
    strata: tuple[MimiiExternalStratumEvidence, ...]
    machine_summaries: tuple[MimiiExternalAggregate, ...]
    domain_summaries: tuple[MimiiExternalAggregate, ...]
    overall_summary: MimiiExternalAggregate
    domain_shift_summary: float


def run_mimii_external_evaluation(
    score_artifact: Path,
    ground_truth_directory: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> MimiiExternalEvaluationResult:
    """Join ground truth with a fixed score artifact and compute external evidence once."""
    _validate_code_revision(code_revision)
    payload = score_artifact.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    document = _score_document(payload)
    scores_by_stratum, scored_clip_count = _scores_by_stratum(document)
    labels_by_stratum = _labels_by_stratum(ground_truth_directory)

    strata: list[MimiiExternalStratumEvidence] = []
    for machine_type in MIMII_MACHINE_TYPES:
        for section in MIMII_EXTERNAL_SECTIONS:
            for domain in ("source", "target"):
                key = (machine_type, section, domain)
                if key not in scores_by_stratum:
                    raise MimiiExternalEvaluationError(f"score artifact is missing stratum {key}")
                if key not in labels_by_stratum:
                    raise MimiiExternalEvaluationError(f"ground truth is missing stratum {key}")
                strata.append(
                    MimiiExternalStratumEvidence(
                        machine_type=machine_type,
                        section=section,
                        domain=domain,
                        evaluation=evaluate_binary_anomaly_ranking(
                            scores_by_stratum[key],
                            labels_by_stratum[key],
                            max_false_positive_rate=MIMII_EXTERNAL_MAX_FALSE_POSITIVE_RATE,
                        ),
                    )
                )

    materialized = tuple(strata)
    if len(materialized) != 30:
        raise MimiiExternalEvaluationError(
            f"external evaluation requires 30 strata, got {len(materialized)}"
        )

    result = MimiiExternalEvaluationResult(
        code_revision=code_revision,
        score_artifact_sha256=digest,
        score_artifact_code_revision=str(document["provenance"]["code_revision"]),
        scored_clip_count=scored_clip_count,
        strata=materialized,
        machine_summaries=tuple(
            _aggregate(
                f"machine:{machine_type}",
                tuple(
                    item.evaluation for item in materialized if item.machine_type == machine_type
                ),
            )
            for machine_type in MIMII_MACHINE_TYPES
        ),
        domain_summaries=tuple(
            _aggregate(
                f"domain:{domain}",
                tuple(item.evaluation for item in materialized if item.domain == domain),
            )
            for domain in ("source", "target")
        ),
        overall_summary=_aggregate(
            "mimii-only:all-strata",
            tuple(item.evaluation for item in materialized),
        ),
        domain_shift_summary=harmonic_mean_unit_interval(
            tuple(
                metric
                for item in materialized
                for metric in (item.evaluation.roc_auc, item.evaluation.partial_roc_auc)
            )
        ),
    )
    write_mimii_external_evaluation_result(result, output_path)
    return result


def write_mimii_external_evaluation_result(
    result: MimiiExternalEvaluationResult,
    output_path: Path,
) -> None:
    """Write one deterministic late-bound external evaluation artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _score_document(payload: bytes) -> Mapping[str, Any]:
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise MimiiExternalEvaluationError(f"invalid score artifact JSON: {error}") from error
    if not isinstance(document, dict):
        raise MimiiExternalEvaluationError("score artifact must be a JSON object")
    if document.get("schema_id") != MIMII_EXTERNAL_SCORE_SCHEMA_ID:
        raise MimiiExternalEvaluationError(
            f"score artifact schema must be {MIMII_EXTERNAL_SCORE_SCHEMA_ID!r}, "
            f"got {document.get('schema_id')!r}"
        )
    label_access = document.get("label_access")
    if not isinstance(label_access, dict) or label_access.get("ground_truth_read") is not False:
        raise MimiiExternalEvaluationError(
            "score artifact must declare that scoring did not read ground truth"
        )
    provenance = document.get("provenance")
    if not isinstance(provenance, dict):
        raise MimiiExternalEvaluationError("score artifact requires provenance")
    if provenance.get("split_id") != MIMII_EXTERNAL_SPLIT_ID:
        raise MimiiExternalEvaluationError(
            f"score artifact split_id must be {MIMII_EXTERNAL_SPLIT_ID!r}"
        )
    if not _FULL_GIT_REVISION.fullmatch(str(provenance.get("code_revision", ""))):
        raise MimiiExternalEvaluationError(
            "score artifact requires a full 40-character code revision"
        )
    return document


def _scores_by_stratum(
    document: Mapping[str, Any],
) -> tuple[dict[tuple[str, str, str], AnomalyScores], int]:
    sections = document.get("section_models")
    if not isinstance(sections, list) or not sections:
        raise MimiiExternalEvaluationError("score artifact requires section_models")

    grouped: dict[tuple[str, str, str], dict[str, float]] = {}
    total = 0
    for section in sections:
        machine_type = str(section["machine_type"])
        section_id = str(section["section"])
        for clip in section["clip_scores"]:
            key = (machine_type, section_id, str(clip["domain"]))
            identity = Path(str(clip["source_file"])).name
            bucket = grouped.setdefault(key, {})
            if identity in bucket:
                raise MimiiExternalEvaluationError(
                    f"score artifact repeats clip identity {identity!r} in stratum {key}"
                )
            bucket[identity] = float(clip["anomaly_score"])
            total += 1

    scores = {
        key: AnomalyScores(
            experiment_id=f"{MIMII_EXTERNAL_CONFIGURATION_ID}--{key[0]}-section-{key[1]}",
            source_observation_ids=tuple(sorted(bucket)),
            scores=tuple(bucket[identity] for identity in sorted(bucket)),
        )
        for key, bucket in grouped.items()
    }
    return scores, total


def _labels_by_stratum(
    directory: Path,
) -> dict[tuple[str, str, str], dict[str, int]]:
    if not directory.is_dir():
        raise MimiiExternalEvaluationError(f"ground-truth directory does not exist: {directory}")

    labels: dict[tuple[str, str, str], dict[str, int]] = {}
    for path in sorted(directory.glob("*.csv")):
        match = _GROUND_TRUTH_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        machine_type = match.group("machine")
        if machine_type not in MIMII_MACHINE_TYPES:
            continue
        section = match.group("section")
        if section not in MIMII_EXTERNAL_SECTIONS:
            raise MimiiExternalEvaluationError(
                f"ground-truth file targets a non-evaluation section: {path.name}"
            )
        key = (machine_type, section, match.group("domain"))
        stratum: dict[str, int] = {}
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if not row:
                    continue
                if len(row) != 2:
                    raise MimiiExternalEvaluationError(
                        f"ground-truth row in {path.name} must have two columns, got {row!r}"
                    )
                identity, raw_label = row[0].strip(), row[1].strip()
                if raw_label not in MIMII_EXTERNAL_LABEL_MAPPING:
                    raise MimiiExternalEvaluationError(
                        f"unsupported ground-truth label {raw_label!r} in {path.name}; "
                        f"expected one of {sorted(MIMII_EXTERNAL_LABEL_MAPPING)}"
                    )
                if identity in stratum:
                    raise MimiiExternalEvaluationError(
                        f"ground-truth file {path.name} repeats identity {identity!r}"
                    )
                stratum[identity] = int(raw_label)
        if not stratum:
            raise MimiiExternalEvaluationError(f"ground-truth file {path.name} is empty")
        labels[key] = stratum
    if not labels:
        raise MimiiExternalEvaluationError(f"no MIMII ground-truth CSV files found in {directory}")
    return labels


def _aggregate(
    scope_id: str,
    evaluations: Sequence[BinaryRankingEvaluation],
) -> MimiiExternalAggregate:
    if not evaluations:
        raise MimiiExternalEvaluationError(f"aggregate {scope_id!r} requires evaluations")
    return MimiiExternalAggregate(
        scope_id=scope_id,
        stratum_count=len(evaluations),
        roc_auc_harmonic_mean=harmonic_mean_unit_interval(
            tuple(item.roc_auc for item in evaluations)
        ),
        partial_roc_auc_harmonic_mean=harmonic_mean_unit_interval(
            tuple(item.partial_roc_auc for item in evaluations)
        ),
    )


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise MimiiExternalEvaluationError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _result_document(result: MimiiExternalEvaluationResult) -> dict[str, Any]:
    manifest = get_dataset(MIMII_DUE_DATASET_ID)
    return {
        "schema_id": MIMII_EXTERNAL_RESULT_SCHEMA_ID,
        "evidence_class": MIMII_EXTERNAL_EVIDENCE_CLASS,
        "provenance": {
            "code_revision": result.code_revision,
            "dataset_id": MIMII_DUE_DATASET_ID,
            "protocol_id": MIMII_DEVELOPMENT_PROTOCOL_ID,
            "configuration_id": MIMII_EXTERNAL_CONFIGURATION_ID,
            "split_id": MIMII_EXTERNAL_SPLIT_ID,
            "dataset_record": {
                "version": manifest.version,
                "provider": manifest.provider,
                "source_url": manifest.source_url,
                "citation_doi": manifest.citation_doi,
                "license": manifest.license_name,
            },
        },
        "score_binding": {
            "score_artifact_sha256": result.score_artifact_sha256,
            "score_artifact_code_revision": result.score_artifact_code_revision,
            "score_semantics": MIMII_EXTERNAL_SCORE_SEMANTICS,
            "scored_clip_count": result.scored_clip_count,
            "label_join": "ground-truth-csv-joined-at-evaluator-edge",
            "label_mapping": dict(MIMII_EXTERNAL_LABEL_MAPPING),
            "ground_truth_record": "https://zenodo.org/records/5257674",
            "note": (
                "Scores were fixed by a label-blind scoring run before any ground truth was "
                "read. This evaluator reads no audio, fits no model, and rescores no clip."
            ),
        },
        "evaluation": {
            "stratum_unit": "machine-type-x-section-x-domain",
            "metrics": ["roc-auc", "standardized-partial-roc-auc:max-fpr=0.1"],
            "max_false_positive_rate": MIMII_EXTERNAL_MAX_FALSE_POSITIVE_RATE,
            "aggregation": "harmonic-mean-with-zero-preserved",
            "dcase_official_score": False,
            "selection_or_threshold_calibration": "none",
            "strata": [_stratum_document(item) for item in result.strata],
            "machine_summaries": [_aggregate_document(item) for item in result.machine_summaries],
            "domain_summaries": [_aggregate_document(item) for item in result.domain_summaries],
            "overall_summary": _aggregate_document(result.overall_summary),
            "mimii_domain_shift_summary": result.domain_shift_summary,
        },
        "capability_scope": {
            "available": list(MIMII_EXTERNAL_AVAILABLE_CAPABILITIES),
            "unsupported_or_not_validated": list(MIMII_EXTERNAL_UNSUPPORTED_CAPABILITIES),
        },
        "interpretation": (
            "Late-bound external evaluation of a configuration frozen before evaluation "
            "sections were opened. Ranking metrics do not create thresholded state, "
            "diagnosis, health indicator, maintenance priority, or RUL."
        ),
    }


def _stratum_document(item: MimiiExternalStratumEvidence) -> dict[str, Any]:
    evaluation = item.evaluation
    return {
        "machine_type": item.machine_type,
        "section": item.section,
        "domain": item.domain,
        "observation_count": evaluation.observation_count,
        "normal_count": evaluation.normal_count,
        "anomaly_count": evaluation.anomaly_count,
        "roc_auc": evaluation.roc_auc,
        "partial_roc_auc": evaluation.partial_roc_auc,
        "max_false_positive_rate": evaluation.max_false_positive_rate,
    }


def _aggregate_document(item: MimiiExternalAggregate) -> dict[str, Any]:
    return {
        "scope_id": item.scope_id,
        "stratum_count": item.stratum_count,
        "roc_auc_harmonic_mean": item.roc_auc_harmonic_mean,
        "partial_roc_auc_harmonic_mean": item.partial_roc_auc_harmonic_mean,
    }
