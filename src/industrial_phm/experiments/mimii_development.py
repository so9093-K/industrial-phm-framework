"""Frozen MIMII DUE development scoring, evaluation, and result schema."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from industrial_phm.adapters import MimiiDueAdapter, validate_mimii_due_source
from industrial_phm.data import get_dataset
from industrial_phm.experiments.binary_ranking import (
    BinaryRankingEvaluation,
    evaluate_binary_anomaly_ranking,
    harmonic_mean_unit_interval,
)
from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_CONFIGURATION_ID,
    MIMII_DEVELOPMENT_FOLD_ID,
    MIMII_DEVELOPMENT_PROTOCOL_ID,
    MIMII_DEVELOPMENT_SECTIONS,
    MIMII_DEVELOPMENT_SPLIT_ID,
    MIMII_DUE_DATASET_ID,
    MIMII_MACHINE_TYPES,
    MimiiSectionScope,
    get_mimii_development_configuration,
    get_mimii_section_configuration,
    iter_mimii_development_section_scopes,
    mimii_expected_train_domain_counts,
)
from industrial_phm.experiments.mimii_model_input import (
    fit_mimii_preprocessing_and_prepare_model_input,
    prepare_mimii_model_scoring_input,
)
from industrial_phm.features import (
    AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
    AudioFeatureVector,
    AudioLogMelRepresentationSpec,
    audio_logmel_feature_names,
    audio_logmel_representation_spec,
    iter_audio_logmel_features,
)
from industrial_phm.models import fit_isolation_forest

MIMII_DEVELOPMENT_RESULT_SCHEMA_ID = "mimii-due-domain-shift-development-result-v1"
MIMII_DEVELOPMENT_EVIDENCE_CLASS = "labeled-offline-development-evidence"

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE = 0.1
MIMII_DEVELOPMENT_AVAILABLE_CAPABILITIES = (
    "clip-level-anomaly-scoring",
    "labeled-offline-development-discrimination-evaluation",
    "source-target-domain-stratified-auc-pauc-evidence",
)
MIMII_DEVELOPMENT_UNSUPPORTED_CAPABILITIES = (
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


class MimiiDevelopmentResultError(ValueError):
    """Raised when MIMII development execution or result evidence violates protocol v1."""


@dataclass(frozen=True, slots=True)
class MimiiSectionDevelopmentInput:
    """Feature vectors needed to execute one machine-section development model."""

    machine_type: str
    section: str
    train_vectors: Sequence[AudioFeatureVector]
    source_test_vectors: Sequence[AudioFeatureVector]
    target_test_vectors: Sequence[AudioFeatureVector]

    def __post_init__(self) -> None:
        scope = MimiiSectionScope(machine_type=self.machine_type, section=self.section)
        object.__setattr__(self, "machine_type", scope.machine_type)
        object.__setattr__(self, "section", scope.section)
        object.__setattr__(self, "train_vectors", tuple(self.train_vectors))
        object.__setattr__(self, "source_test_vectors", tuple(self.source_test_vectors))
        object.__setattr__(self, "target_test_vectors", tuple(self.target_test_vectors))


@dataclass(frozen=True, slots=True)
class MimiiSectionDevelopmentEvidence:
    """Fit, score, and label-late-bound evidence for one section model."""

    machine_type: str
    section: str
    experiment_id: str
    source_train_count: int
    target_train_count: int
    preprocessing_fit_count: int
    reference_count: int
    model_fit_count: int
    fitted_center: tuple[float, ...]
    fitted_scale: tuple[float, ...]
    zero_iqr_features: tuple[str, ...]
    source_scoring_count: int
    target_scoring_count: int
    source_evaluation: BinaryRankingEvaluation
    target_evaluation: BinaryRankingEvaluation

    def __post_init__(self) -> None:
        scope = MimiiSectionScope(machine_type=self.machine_type, section=self.section)
        expected_config = get_mimii_section_configuration(scope.machine_type, scope.section)
        if self.experiment_id != expected_config.experiment_id:
            raise MimiiDevelopmentResultError(
                "section evidence experiment_id must match the protocol-resolved configuration"
            )
        for field_name in (
            "source_train_count",
            "target_train_count",
            "preprocessing_fit_count",
            "reference_count",
            "model_fit_count",
            "source_scoring_count",
            "target_scoring_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise MimiiDevelopmentResultError(f"{field_name} must be a positive integer")
        if (
            len(
                {
                    self.preprocessing_fit_count,
                    self.reference_count,
                    self.model_fit_count,
                }
            )
            != 1
        ):
            raise MimiiDevelopmentResultError(
                "MIMII section preprocessing/reference/model-fit counts must be identical"
            )
        if self.source_train_count + self.target_train_count != self.model_fit_count:
            raise MimiiDevelopmentResultError(
                "MIMII section source/target train counts must sum to model_fit_count"
            )
        expected_source, expected_target = mimii_expected_train_domain_counts(
            self.machine_type,
            self.section,
        )
        if (self.source_train_count, self.target_train_count) != (
            expected_source,
            expected_target,
        ):
            raise MimiiDevelopmentResultError(
                "MIMII section train counts do not match the verified source profile"
            )
        _validate_preprocessing_values(
            self.fitted_center,
            self.fitted_scale,
            self.zero_iqr_features,
        )
        if self.source_evaluation.observation_count != self.source_scoring_count:
            raise MimiiDevelopmentResultError(
                "source evaluation count must match source scoring count"
            )
        if self.target_evaluation.observation_count != self.target_scoring_count:
            raise MimiiDevelopmentResultError(
                "target evaluation count must match target scoring count"
            )
        for evaluation in (self.source_evaluation, self.target_evaluation):
            if evaluation.max_false_positive_rate != MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE:
                raise MimiiDevelopmentResultError(
                    "MIMII section pAUC max_false_positive_rate must be 0.1"
                )


@dataclass(frozen=True, slots=True)
class MimiiAggregateEvidence:
    """Harmonic AUC/pAUC summary over a named set of development strata."""

    scope_id: str
    stratum_count: int
    roc_auc_harmonic_mean: float
    partial_roc_auc_harmonic_mean: float

    def __post_init__(self) -> None:
        if not self.scope_id.strip() or self.scope_id != self.scope_id.strip():
            raise MimiiDevelopmentResultError("aggregate scope_id must be trimmed and non-empty")
        if isinstance(self.stratum_count, bool) or self.stratum_count <= 0:
            raise MimiiDevelopmentResultError("aggregate stratum_count must be positive")
        for field_name in ("roc_auc_harmonic_mean", "partial_roc_auc_harmonic_mean"):
            value = getattr(self, field_name)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise MimiiDevelopmentResultError(
                    f"aggregate {field_name} must be a finite unit-interval metric"
                )


@dataclass(frozen=True, slots=True)
class MimiiDevelopmentResult:
    """Serializable evidence for the frozen MIMII DUE development protocol."""

    code_revision: str
    verified_source_clip_count: int
    protocol_id: str
    configuration_id: str
    dataset_id: str
    dataset_version: str
    dataset_provider: str
    dataset_source_url: str
    dataset_citation_doi: str
    dataset_license_name: str
    split_id: str
    fold_id: str
    feature_set_id: str
    selected_features: tuple[str, ...]
    representation: AudioLogMelRepresentationSpec
    fit_partition: str
    scaling_strategy: str
    reference_strategy: str
    sampling_policy_id: str
    model_family: str
    model_parameters: tuple[tuple[str, ExperimentParameter], ...]
    random_seed: int
    section_results: tuple[MimiiSectionDevelopmentEvidence, ...]
    machine_summaries: tuple[MimiiAggregateEvidence, ...]
    domain_summaries: tuple[MimiiAggregateEvidence, ...]
    overall_summary: MimiiAggregateEvidence
    mimii_domain_shift_summary: float

    def __post_init__(self) -> None:
        _validate_code_revision(self.code_revision)
        if (
            isinstance(self.verified_source_clip_count, bool)
            or not isinstance(self.verified_source_clip_count, int)
            or self.verified_source_clip_count <= 0
        ):
            raise MimiiDevelopmentResultError(
                "verified_source_clip_count must be a positive integer"
            )
        if self.protocol_id != MIMII_DEVELOPMENT_PROTOCOL_ID:
            raise MimiiDevelopmentResultError("protocol_id does not match MIMII development v1")
        if self.configuration_id != MIMII_DEVELOPMENT_CONFIGURATION_ID:
            raise MimiiDevelopmentResultError(
                "configuration_id does not match MIMII development v1"
            )
        if self.dataset_id != MIMII_DUE_DATASET_ID:
            raise MimiiDevelopmentResultError("dataset_id does not match MIMII DUE")
        manifest = get_dataset(MIMII_DUE_DATASET_ID)
        expected_source_record = (
            ("dataset_version", self.dataset_version, manifest.version),
            ("dataset_provider", self.dataset_provider, manifest.provider),
            ("dataset_source_url", self.dataset_source_url, manifest.source_url),
            ("dataset_citation_doi", self.dataset_citation_doi, manifest.citation_doi),
            ("dataset_license_name", self.dataset_license_name, manifest.license_name),
        )
        for field_name, observed, expected in expected_source_record:
            if observed != expected:
                raise MimiiDevelopmentResultError(
                    f"{field_name} does not match packaged MIMII dataset manifest"
                )
        if self.split_id != MIMII_DEVELOPMENT_SPLIT_ID:
            raise MimiiDevelopmentResultError("split_id does not match MIMII development v1")
        if self.fold_id != MIMII_DEVELOPMENT_FOLD_ID:
            raise MimiiDevelopmentResultError("fold_id does not match MIMII development v1")
        if self.feature_set_id != AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID:
            raise MimiiDevelopmentResultError("feature_set_id does not match audio protocol v1")
        if self.selected_features != audio_logmel_feature_names():
            raise MimiiDevelopmentResultError("selected_features do not match audio protocol v1")
        if not isinstance(self.representation, AudioLogMelRepresentationSpec):
            raise MimiiDevelopmentResultError(
                "representation must be AudioLogMelRepresentationSpec"
            )
        if self.representation != audio_logmel_representation_spec():
            raise MimiiDevelopmentResultError(
                "representation parameters do not match audio-logmel-statistical-v1"
            )

        config = get_mimii_development_configuration()
        expected_axes = (
            ("fit_partition", self.fit_partition, config.fit_partition.value),
            ("scaling_strategy", self.scaling_strategy, config.scaling_strategy.value),
            ("reference_strategy", self.reference_strategy, config.reference_strategy.value),
            ("sampling_policy_id", self.sampling_policy_id, config.sampling_policy_id),
            ("model_family", self.model_family, config.model_family.value),
            ("random_seed", self.random_seed, config.random_seed),
            (
                "model_parameters",
                self.model_parameters,
                tuple(sorted(config.model_parameters.items())),
            ),
        )
        for field_name, observed, expected in expected_axes:
            if observed != expected:
                raise MimiiDevelopmentResultError(
                    f"{field_name} does not match the frozen MIMII development configuration"
                )

        ordered_sections = _ordered_complete_section_results(self.section_results)
        if self.section_results != ordered_sections:
            raise MimiiDevelopmentResultError(
                "MIMII section results must use deterministic machine-major order"
            )

        (
            expected_machine_summaries,
            expected_domain_summaries,
            expected_overall,
            expected_combined,
        ) = _aggregate_complete_section_results(self.section_results)
        if self.machine_summaries != expected_machine_summaries:
            raise MimiiDevelopmentResultError(
                "machine summaries do not match section-level evaluation evidence"
            )
        if self.domain_summaries != expected_domain_summaries:
            raise MimiiDevelopmentResultError(
                "domain summaries do not match section-level evaluation evidence"
            )
        if self.overall_summary != expected_overall:
            raise MimiiDevelopmentResultError(
                "overall summary does not match section-level evaluation evidence"
            )
        if self.mimii_domain_shift_summary != expected_combined:
            raise MimiiDevelopmentResultError(
                "mimii_domain_shift_summary does not match section-level evaluation evidence"
            )


def evaluate_mimii_section_development(
    section_input: MimiiSectionDevelopmentInput,
) -> MimiiSectionDevelopmentEvidence:
    """Fit and evaluate one frozen section model with labels joined only after scoring."""
    config = get_mimii_section_configuration(
        section_input.machine_type,
        section_input.section,
    )
    state, fit_input = fit_mimii_preprocessing_and_prepare_model_input(
        config,
        section_input.train_vectors,
    )
    model = fit_isolation_forest(config, fit_input)

    source_scoring_input = prepare_mimii_model_scoring_input(
        config,
        state,
        section_input.source_test_vectors,
        domain="source",
    )
    source_scores = model.score(source_scoring_input)
    source_evaluation = evaluate_binary_anomaly_ranking(
        source_scores,
        _labels_by_source_identity(section_input.source_test_vectors),
        max_false_positive_rate=MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
    )

    target_scoring_input = prepare_mimii_model_scoring_input(
        config,
        state,
        section_input.target_test_vectors,
        domain="target",
    )
    target_scores = model.score(target_scoring_input)
    target_evaluation = evaluate_binary_anomaly_ranking(
        target_scores,
        _labels_by_source_identity(section_input.target_test_vectors),
        max_false_positive_rate=MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
    )

    source_train_count = sum(
        vector.metadata.get("domain") == "source" for vector in section_input.train_vectors
    )
    target_train_count = len(section_input.train_vectors) - source_train_count
    return MimiiSectionDevelopmentEvidence(
        machine_type=section_input.machine_type,
        section=section_input.section,
        experiment_id=config.experiment_id,
        source_train_count=source_train_count,
        target_train_count=target_train_count,
        preprocessing_fit_count=state.observation_count,
        reference_count=fit_input.reference_observation_count,
        model_fit_count=fit_input.fit_observation_count,
        fitted_center=tuple(state.fitted_center),
        fitted_scale=tuple(state.fitted_scale),
        zero_iqr_features=tuple(state.zero_iqr_features),
        source_scoring_count=source_scores.observation_count,
        target_scoring_count=target_scores.observation_count,
        source_evaluation=source_evaluation,
        target_evaluation=target_evaluation,
    )


def run_mimii_development_evaluation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> MimiiDevelopmentResult:
    """Run the frozen MIMII development path section-by-section and write evidence."""
    _validate_code_revision(code_revision)
    source_report = validate_mimii_due_source(source)
    if not source_report.profile_matches:
        raise MimiiDevelopmentResultError(
            "MIMII DUE source does not match the verified v1.01 profile: "
            + "; ".join(source_report.profile_issues)
        )

    adapter = MimiiDueAdapter()

    def section_inputs() -> Iterable[MimiiSectionDevelopmentInput]:
        for scope in iter_mimii_development_section_scopes():
            vectors = tuple(
                iter_audio_logmel_features(
                    adapter.iter_section_series(
                        source,
                        group="dev",
                        machine_type=scope.machine_type,
                        section=scope.section,
                    )
                )
            )
            train_vectors = tuple(
                vector for vector in vectors if vector.metadata.get("split") == "train"
            )
            source_test_vectors = tuple(
                vector
                for vector in vectors
                if vector.metadata.get("split") == "test"
                and vector.metadata.get("domain") == "source"
            )
            target_test_vectors = tuple(
                vector
                for vector in vectors
                if vector.metadata.get("split") == "test"
                and vector.metadata.get("domain") == "target"
            )
            yield MimiiSectionDevelopmentInput(
                machine_type=scope.machine_type,
                section=scope.section,
                train_vectors=train_vectors,
                source_test_vectors=source_test_vectors,
                target_test_vectors=target_test_vectors,
            )

    result = evaluate_mimii_development(
        section_inputs(),
        code_revision=code_revision,
        source_clip_count=source_report.clip_count,
    )
    write_mimii_development_result(result, output_path)
    return result


def evaluate_mimii_development(
    section_inputs: Iterable[MimiiSectionDevelopmentInput],
    *,
    code_revision: str,
    source_clip_count: int,
) -> MimiiDevelopmentResult:
    """Evaluate section inputs sequentially and aggregate the complete development result."""
    _validate_code_revision(code_revision)
    section_results = tuple(
        evaluate_mimii_section_development(section_input) for section_input in section_inputs
    )
    return build_mimii_development_result(
        section_results,
        code_revision=code_revision,
        source_clip_count=source_clip_count,
    )


def build_mimii_development_result(
    section_results: Sequence[MimiiSectionDevelopmentEvidence],
    *,
    code_revision: str,
    source_clip_count: int,
) -> MimiiDevelopmentResult:
    """Aggregate exactly fifteen section-model results into one immutable evidence object."""
    _validate_code_revision(code_revision)
    if (
        isinstance(source_clip_count, bool)
        or not isinstance(source_clip_count, int)
        or source_clip_count <= 0
    ):
        raise MimiiDevelopmentResultError("source_clip_count must be a positive integer")
    ordered = _ordered_complete_section_results(section_results)
    config = get_mimii_development_configuration()
    manifest = get_dataset(MIMII_DUE_DATASET_ID)
    if manifest.citation_doi is None:
        raise MimiiDevelopmentResultError(
            "MIMII packaged dataset manifest must declare citation_doi"
        )

    (
        machine_summaries,
        domain_summaries,
        overall_summary,
        mimii_domain_shift_summary,
    ) = _aggregate_complete_section_results(ordered)

    return MimiiDevelopmentResult(
        code_revision=code_revision,
        verified_source_clip_count=source_clip_count,
        protocol_id=MIMII_DEVELOPMENT_PROTOCOL_ID,
        configuration_id=MIMII_DEVELOPMENT_CONFIGURATION_ID,
        dataset_id=config.dataset_id,
        dataset_version=manifest.version,
        dataset_provider=manifest.provider,
        dataset_source_url=manifest.source_url,
        dataset_citation_doi=manifest.citation_doi,
        dataset_license_name=manifest.license_name,
        split_id=config.split_id,
        fold_id=config.fold_id,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        representation=audio_logmel_representation_spec(),
        fit_partition=config.fit_partition.value,
        scaling_strategy=config.scaling_strategy.value,
        reference_strategy=config.reference_strategy.value,
        sampling_policy_id=config.sampling_policy_id,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        section_results=ordered,
        machine_summaries=machine_summaries,
        domain_summaries=domain_summaries,
        overall_summary=overall_summary,
        mimii_domain_shift_summary=mimii_domain_shift_summary,
    )


def write_mimii_development_result(
    result: MimiiDevelopmentResult,
    output_path: Path,
) -> None:
    """Write deterministic JSON for the preregistered MIMII development evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ordered_complete_section_results(
    section_results: Sequence[MimiiSectionDevelopmentEvidence],
) -> tuple[MimiiSectionDevelopmentEvidence, ...]:
    by_scope: dict[tuple[str, str], MimiiSectionDevelopmentEvidence] = {}
    for result in section_results:
        key = (result.machine_type, result.section)
        if key in by_scope:
            raise MimiiDevelopmentResultError(
                f"duplicate MIMII section result: {result.machine_type}/section-{result.section}"
            )
        by_scope[key] = result

    expected_scopes = iter_mimii_development_section_scopes()
    expected_keys = {(scope.machine_type, scope.section) for scope in expected_scopes}
    observed_keys = set(by_scope)
    if observed_keys != expected_keys:
        raise MimiiDevelopmentResultError(
            "MIMII section results must cover all development scopes; "
            f"missing={sorted(expected_keys - observed_keys)}, "
            f"unexpected={sorted(observed_keys - expected_keys)}"
        )
    return tuple(by_scope[(scope.machine_type, scope.section)] for scope in expected_scopes)


def _aggregate_complete_section_results(
    section_results: Sequence[MimiiSectionDevelopmentEvidence],
) -> tuple[
    tuple[MimiiAggregateEvidence, ...],
    tuple[MimiiAggregateEvidence, ...],
    MimiiAggregateEvidence,
    float,
]:
    machine_summaries = tuple(
        _aggregate(
            f"machine:{machine_type}",
            tuple(
                evaluation
                for result in section_results
                if result.machine_type == machine_type
                for evaluation in (result.source_evaluation, result.target_evaluation)
            ),
        )
        for machine_type in MIMII_MACHINE_TYPES
    )
    domain_summaries = tuple(
        _aggregate(
            f"domain:{domain}",
            tuple(
                result.source_evaluation if domain == "source" else result.target_evaluation
                for result in section_results
            ),
        )
        for domain in ("source", "target")
    )
    all_evaluations = tuple(
        evaluation
        for result in section_results
        for evaluation in (result.source_evaluation, result.target_evaluation)
    )
    overall_summary = _aggregate("mimii-only:all-strata", all_evaluations)
    combined_summary = harmonic_mean_unit_interval(
        tuple(
            metric
            for evaluation in all_evaluations
            for metric in (evaluation.roc_auc, evaluation.partial_roc_auc)
        )
    )
    return machine_summaries, domain_summaries, overall_summary, combined_summary


def _aggregate(
    scope_id: str,
    evaluations: Sequence[BinaryRankingEvaluation],
) -> MimiiAggregateEvidence:
    if not evaluations:
        raise MimiiDevelopmentResultError(f"aggregate {scope_id!r} requires evaluations")
    return MimiiAggregateEvidence(
        scope_id=scope_id,
        stratum_count=len(evaluations),
        roc_auc_harmonic_mean=harmonic_mean_unit_interval(
            tuple(item.roc_auc for item in evaluations)
        ),
        partial_roc_auc_harmonic_mean=harmonic_mean_unit_interval(
            tuple(item.partial_roc_auc for item in evaluations)
        ),
    )


def _labels_by_source_identity(
    vectors: Sequence[AudioFeatureVector],
) -> Mapping[str, int]:
    labels: dict[str, int] = {}
    for index, vector in enumerate(vectors):
        source_file = vector.metadata.get("source_file")
        if not isinstance(source_file, str) or not source_file.strip():
            raise MimiiDevelopmentResultError(
                f"MIMII evaluation vector {index} requires source_file identity"
            )
        if source_file in labels:
            raise MimiiDevelopmentResultError(
                f"MIMII evaluation source identity repeats: {source_file!r}"
            )
        label = vector.metadata.get("clip_label")
        if label == "normal":
            labels[source_file] = 0
        elif label == "anomaly":
            labels[source_file] = 1
        else:
            raise MimiiDevelopmentResultError(
                f"MIMII evaluation vector {index} requires normal/anomaly clip_label"
            )
    return labels


def _validate_preprocessing_values(
    fitted_center: Sequence[float],
    fitted_scale: Sequence[float],
    zero_iqr_features: Sequence[str],
) -> None:
    expected_width = len(audio_logmel_feature_names())
    if len(fitted_center) != expected_width or len(fitted_scale) != expected_width:
        raise MimiiDevelopmentResultError(
            "MIMII section preprocessing vectors must match the 128-feature schema"
        )
    if not all(math.isfinite(value) for value in fitted_center):
        raise MimiiDevelopmentResultError("MIMII fitted_center must contain finite values")
    if not all(math.isfinite(value) and value > 0.0 for value in fitted_scale):
        raise MimiiDevelopmentResultError("MIMII fitted_scale must contain finite positive values")
    unknown_zero_iqr = sorted(set(zero_iqr_features) - set(audio_logmel_feature_names()))
    if unknown_zero_iqr:
        raise MimiiDevelopmentResultError(
            f"MIMII zero_iqr_features contains unknown features: {unknown_zero_iqr}"
        )


def _result_document(result: MimiiDevelopmentResult) -> dict[str, Any]:
    spec = result.representation
    return {
        "schema_id": MIMII_DEVELOPMENT_RESULT_SCHEMA_ID,
        "provenance": {
            "code_revision": result.code_revision,
            "protocol_id": result.protocol_id,
            "configuration_id": result.configuration_id,
            "dataset_id": result.dataset_id,
            "split_id": result.split_id,
            "fold_id": result.fold_id,
            "evidence_class": MIMII_DEVELOPMENT_EVIDENCE_CLASS,
        },
        "source_scope": {
            "dataset_record": {
                "version": result.dataset_version,
                "provider": result.dataset_provider,
                "source_url": result.dataset_source_url,
                "citation_doi": result.dataset_citation_doi,
                "license": result.dataset_license_name,
            },
            "verified_source_clip_count": result.verified_source_clip_count,
            "source_group": "dev",
            "machine_types": list(MIMII_MACHINE_TYPES),
            "sections": list(MIMII_DEVELOPMENT_SECTIONS),
            "train_domains": ["source", "target"],
            "scoring_domains": ["source", "target"],
            "excluded": [
                "eval:sections-03-05",
                "development-test-labels-from-model-fit-and-scoring",
            ],
        },
        "representation": {
            "feature_set_id": result.feature_set_id,
            "selected_features": list(result.selected_features),
            "selected_feature_count": len(result.selected_features),
            "sample_rate_hz": spec.sample_rate_hz,
            "sample_count": spec.sample_count,
            "pcm_full_scale_divisor": spec.pcm_full_scale_divisor,
            "frame_length_samples": spec.frame_length_samples,
            "hop_length_samples": spec.hop_length_samples,
            "window": spec.window,
            "centering": spec.centering,
            "padding": spec.padding,
            "fft_size": spec.fft_size,
            "power_normalization": spec.power_normalization,
            "mel_scale": spec.mel_scale,
            "mel_band_count": spec.mel_band_count,
            "minimum_frequency_hz": spec.minimum_frequency_hz,
            "maximum_frequency_hz": spec.maximum_frequency_hz,
            "mel_filter_normalization": spec.mel_filter_normalization,
            "log_floor": spec.log_floor,
            "frame_count": spec.frame_count,
            "feature_count": spec.feature_count,
            "clip_aggregation": spec.clip_aggregation,
        },
        "preprocessing": {
            "fit_partition": result.fit_partition,
            "scaling_strategy": result.scaling_strategy,
            "fit_scope": "per-machine-section-complete-normal-train",
        },
        "model": {
            "model_family": result.model_family,
            "parameters": dict(result.model_parameters),
            "random_seed": result.random_seed,
            "reference_strategy": result.reference_strategy,
            "sampling_policy_id": result.sampling_policy_id,
            "score_semantics": "higher-is-more-anomalous",
            "model_unit": "machine-type-x-section",
        },
        "section_models": [_section_document(item) for item in result.section_results],
        "evaluation": {
            "label_join": "source-file-identity-at-evaluator-edge",
            "stratum_unit": "machine-type-x-section-x-domain",
            "metrics": [
                "roc-auc",
                "standardized-partial-roc-auc:max-fpr=0.1",
            ],
            "max_false_positive_rate": MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
            "aggregation": "harmonic-mean-with-zero-preserved",
            "machine_summaries": [_aggregate_document(item) for item in result.machine_summaries],
            "domain_summaries": [_aggregate_document(item) for item in result.domain_summaries],
            "overall_summary": _aggregate_document(result.overall_summary),
            "mimii_domain_shift_summary": result.mimii_domain_shift_summary,
            "dcase_official_score": False,
        },
        "capability": {
            "available": list(MIMII_DEVELOPMENT_AVAILABLE_CAPABILITIES),
            "unsupported": list(MIMII_DEVELOPMENT_UNSUPPORTED_CAPABILITIES),
        },
    }


def _section_document(result: MimiiSectionDevelopmentEvidence) -> dict[str, Any]:
    return {
        "machine_type": result.machine_type,
        "section": result.section,
        "experiment_id": result.experiment_id,
        "population_flow": {
            "source_train_clip_count": result.source_train_count,
            "target_train_clip_count": result.target_train_count,
            "preprocessing_fit_clip_count": result.preprocessing_fit_count,
            "reference_clip_count": result.reference_count,
            "model_fit_clip_count": result.model_fit_count,
            "source_scoring_clip_count": result.source_scoring_count,
            "target_scoring_clip_count": result.target_scoring_count,
        },
        "preprocessing_state": {
            "fitted_center": list(result.fitted_center),
            "fitted_scale": list(result.fitted_scale),
            "zero_iqr_features": list(result.zero_iqr_features),
        },
        "evaluation": {
            "source": _evaluation_document(result.source_evaluation),
            "target": _evaluation_document(result.target_evaluation),
        },
    }


def _evaluation_document(evaluation: BinaryRankingEvaluation) -> dict[str, Any]:
    return {
        "observation_count": evaluation.observation_count,
        "normal_count": evaluation.normal_count,
        "anomaly_count": evaluation.anomaly_count,
        "roc_auc": evaluation.roc_auc,
        "partial_roc_auc": evaluation.partial_roc_auc,
        "max_false_positive_rate": evaluation.max_false_positive_rate,
    }


def _aggregate_document(summary: MimiiAggregateEvidence) -> dict[str, Any]:
    return {
        "scope_id": summary.scope_id,
        "stratum_count": summary.stratum_count,
        "roc_auc_harmonic_mean": summary.roc_auc_harmonic_mean,
        "partial_roc_auc_harmonic_mean": summary.partial_roc_auc_harmonic_mean,
    }


def _validate_code_revision(value: str) -> None:
    if not isinstance(value, str) or not _FULL_GIT_REVISION.fullmatch(value):
        raise MimiiDevelopmentResultError(
            "code_revision must be a full lowercase 40-character Git SHA"
        )
