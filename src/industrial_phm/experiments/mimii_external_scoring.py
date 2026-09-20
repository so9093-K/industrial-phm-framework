"""Label-blind MIMII DUE external scoring for evaluation sections 03-05.

This module deliberately has no ground-truth reader. It fits fresh section models on the
sections 03-05 normal train population and scores evaluation-test clips that carry no
condition label in their filenames or metadata. The resulting score artifact is immutable
evidence that a later evaluator joins with ground truth at its own edge.

Nothing here imports, opens, or infers a condition label. Adding such a path would let the
evaluation label reach model fitting or scoring, which the protocol forbids.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from industrial_phm.adapters import (
    MimiiDueAdapter,
    iter_mimii_evaluation_test_clips,
    read_mimii_evaluation_test_series,
    validate_mimii_due_source,
    validate_mimii_evaluation_test_source,
)
from industrial_phm.data import get_dataset
from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_PROTOCOL_ID,
    MIMII_DUE_DATASET_ID,
    MIMII_EXTERNAL_CONFIGURATION_ID,
    MIMII_EXTERNAL_SECTIONS,
    MIMII_EXTERNAL_SPLIT_ID,
    MimiiSectionScope,
    get_mimii_external_section_configuration,
    iter_mimii_external_section_scopes,
    mimii_expected_train_domain_counts,
)
from industrial_phm.experiments.mimii_model_input import (
    fit_mimii_preprocessing_and_prepare_model_input,
    prepare_mimii_model_scoring_input,
)
from industrial_phm.features import (
    AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
    AudioFeatureVector,
    audio_logmel_representation_spec,
    iter_audio_logmel_features,
)
from industrial_phm.models import fit_isolation_forest

MIMII_EXTERNAL_SCORE_SCHEMA_ID = "mimii-due-domain-shift-external-score-v1"
MIMII_EXTERNAL_SCORE_EVIDENCE_CLASS = "label-blind-external-anomaly-score"
MIMII_EXTERNAL_SCORE_SEMANTICS = "higher-is-more-anomalous"

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_DOMAINS: tuple[Literal["source", "target"], ...] = ("source", "target")


class MimiiExternalScoringError(ValueError):
    """Raised when label-blind external scoring violates its protocol boundary."""


@dataclass(frozen=True, slots=True)
class MimiiExternalClipScore:
    """One evaluation-test clip score with its label-free source identity."""

    source_file: str
    domain: str
    anomaly_score: float


@dataclass(frozen=True, slots=True)
class MimiiExternalSectionScores:
    """Fitted-population provenance and clip scores for one external section model."""

    experiment_id: str
    machine_type: str
    section: str
    source_train_clip_count: int
    target_train_clip_count: int
    model_fit_clip_count: int
    scores: tuple[MimiiExternalClipScore, ...]

    @property
    def scored_clip_count(self) -> int:
        """Return how many evaluation-test clips this section scored."""
        return len(self.scores)


@dataclass(frozen=True, slots=True)
class MimiiExternalScoreResult:
    """Immutable label-blind score evidence for evaluation sections 03-05."""

    code_revision: str
    verified_train_clip_count: int
    verified_evaluation_clip_count: int
    sections: tuple[MimiiExternalSectionScores, ...]

    @property
    def scored_clip_count(self) -> int:
        """Return the total number of scored evaluation-test clips."""
        return sum(section.scored_clip_count for section in self.sections)


def run_mimii_external_scoring(
    source: Path,
    evaluation_source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> MimiiExternalScoreResult:
    """Fit sections 03-05 models and score evaluation-test clips without any label."""
    _validate_code_revision(code_revision)

    train_report = validate_mimii_due_source(source)
    if not train_report.profile_matches:
        raise MimiiExternalScoringError(
            "MIMII DUE prepared source does not match the verified profile: "
            + "; ".join(train_report.profile_issues)
        )
    evaluation_report = validate_mimii_evaluation_test_source(evaluation_source)
    if not evaluation_report.profile_matches:
        raise MimiiExternalScoringError(
            "MIMII DUE evaluation-test source does not match the verified profile: "
            + "; ".join(evaluation_report.profile_issues)
        )

    adapter = MimiiDueAdapter()
    sections = tuple(
        _score_section(adapter, source, evaluation_source, scope)
        for scope in iter_mimii_external_section_scopes()
    )
    result = MimiiExternalScoreResult(
        code_revision=code_revision,
        verified_train_clip_count=train_report.clip_count,
        verified_evaluation_clip_count=evaluation_report.clip_count,
        sections=sections,
    )
    if result.scored_clip_count != evaluation_report.clip_count:
        raise MimiiExternalScoringError(
            "scored clip count must cover the verified evaluation-test population; "
            f"scored={result.scored_clip_count}, verified={evaluation_report.clip_count}"
        )
    write_mimii_external_score_result(result, output_path)
    return result


def write_mimii_external_score_result(
    result: MimiiExternalScoreResult,
    output_path: Path,
) -> None:
    """Write one deterministic, immutable label-blind score artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _score_section(
    adapter: MimiiDueAdapter,
    source: Path,
    evaluation_source: Path,
    scope: MimiiSectionScope,
) -> MimiiExternalSectionScores:
    config = get_mimii_external_section_configuration(scope.machine_type, scope.section)
    train_vectors = tuple(
        iter_audio_logmel_features(
            adapter.iter_section_series(
                source,
                group="eval",
                machine_type=scope.machine_type,
                section=scope.section,
            )
        )
    )
    preprocessing_state, fit_input = fit_mimii_preprocessing_and_prepare_model_input(
        config,
        train_vectors,
    )
    model = fit_isolation_forest(config, fit_input)

    scores: list[MimiiExternalClipScore] = []
    for domain in _DOMAINS:
        clips = iter_mimii_evaluation_test_clips(
            evaluation_source,
            machine_type=scope.machine_type,
            section=scope.section,
            domain=domain,
        )
        vectors = tuple(
            iter_audio_logmel_features(
                read_mimii_evaluation_test_series(evaluation_source, clip) for clip in clips
            )
        )
        _validate_label_free_vectors(vectors, scope=scope, domain=domain)
        scoring_input = prepare_mimii_model_scoring_input(
            config,
            preprocessing_state,
            vectors,
            domain=domain,
        )
        anomaly_scores = model.score(scoring_input)
        scores.extend(
            MimiiExternalClipScore(
                source_file=observation_id,
                domain=domain,
                anomaly_score=float(score),
            )
            for observation_id, score in zip(
                anomaly_scores.source_observation_ids,
                anomaly_scores.scores,
                strict=True,
            )
        )

    expected_source, expected_target = mimii_expected_train_domain_counts(
        scope.machine_type,
        scope.section,
    )
    return MimiiExternalSectionScores(
        experiment_id=config.experiment_id,
        machine_type=scope.machine_type,
        section=scope.section,
        source_train_clip_count=expected_source,
        target_train_clip_count=expected_target,
        model_fit_clip_count=fit_input.fit_observation_count,
        scores=tuple(sorted(scores, key=lambda item: item.source_file)),
    )


def _validate_label_free_vectors(
    vectors: Sequence[AudioFeatureVector],
    *,
    scope: MimiiSectionScope,
    domain: str,
) -> None:
    """Refuse any evaluation-test vector that carries a condition label."""
    if not vectors:
        raise MimiiExternalScoringError(
            f"no evaluation-test clips for {scope.machine_type}/section-{scope.section}/{domain}"
        )
    for index, vector in enumerate(vectors):
        leaked = sorted(key for key in vector.metadata if "label" in key)
        if leaked:
            raise MimiiExternalScoringError(
                f"evaluation-test vector {index} carries label metadata {leaked}; "
                "external scoring must stay label-blind"
            )


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise MimiiExternalScoringError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _configuration_document(config: ExperimentConfig) -> dict[str, Any]:
    spec = audio_logmel_representation_spec()
    return {
        "feature_set_id": AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
        "selected_feature_count": len(config.selected_features),
        "mel_band_count": spec.mel_band_count,
        "reference_strategy": config.reference_strategy.value,
        "sampling_policy_id": config.sampling_policy_id,
        "scaling_strategy": config.scaling_strategy.value,
        "model_family": config.model_family.value,
        "model_parameters": dict(config.model_parameters),
        "random_seed": config.random_seed,
        "score_semantics": MIMII_EXTERNAL_SCORE_SEMANTICS,
    }


def _result_document(result: MimiiExternalScoreResult) -> dict[str, Any]:
    manifest = get_dataset(MIMII_DUE_DATASET_ID)
    base = get_mimii_external_section_configuration("fan", "03")
    return {
        "schema_id": MIMII_EXTERNAL_SCORE_SCHEMA_ID,
        "evidence_class": MIMII_EXTERNAL_SCORE_EVIDENCE_CLASS,
        "provenance": {
            "code_revision": result.code_revision,
            "dataset_id": MIMII_DUE_DATASET_ID,
            "protocol_id": MIMII_DEVELOPMENT_PROTOCOL_ID,
            "configuration_id": MIMII_EXTERNAL_CONFIGURATION_ID,
            "split_id": MIMII_EXTERNAL_SPLIT_ID,
        },
        "source_scope": {
            "dataset_record": {
                "version": manifest.version,
                "provider": manifest.provider,
                "source_url": manifest.source_url,
                "citation_doi": manifest.citation_doi,
                "license": manifest.license_name,
            },
            "train_group": "eval",
            "sections": list(MIMII_EXTERNAL_SECTIONS),
            "verified_train_clip_count": result.verified_train_clip_count,
            "verified_evaluation_clip_count": result.verified_evaluation_clip_count,
            "evaluation_test_record": "https://zenodo.org/records/4884786",
        },
        "configuration": _configuration_document(base),
        "label_access": {
            "ground_truth_read": False,
            "note": (
                "Evaluation-test filenames and clip metadata carry no condition label, and "
                "this scoring path has no ground-truth reader. Labels are joined only by a "
                "later evaluator against this immutable artifact."
            ),
        },
        "scored_clip_count": result.scored_clip_count,
        "section_models": [_section_document(section) for section in result.sections],
    }


def _section_document(section: MimiiExternalSectionScores) -> dict[str, Any]:
    return {
        "experiment_id": section.experiment_id,
        "machine_type": section.machine_type,
        "section": section.section,
        "population_flow": {
            "source_train_clip_count": section.source_train_clip_count,
            "target_train_clip_count": section.target_train_clip_count,
            "model_fit_clip_count": section.model_fit_clip_count,
            "scored_clip_count": section.scored_clip_count,
        },
        "clip_scores": [
            {
                "source_file": score.source_file,
                "domain": score.domain,
                "anomaly_score": score.anomaly_score,
            }
            for score in section.scores
        ],
    }
