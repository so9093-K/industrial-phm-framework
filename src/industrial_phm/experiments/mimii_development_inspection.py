"""Schema-specific inspection for MIMII DUE domain-shift development evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from industrial_phm.data import get_dataset
from industrial_phm.experiments.binary_ranking import harmonic_mean_unit_interval
from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_CONFIGURATION_ID,
    MIMII_DEVELOPMENT_FOLD_ID,
    MIMII_DEVELOPMENT_PROTOCOL_ID,
    MIMII_DEVELOPMENT_SECTIONS,
    MIMII_DEVELOPMENT_SPLIT_ID,
    MIMII_DUE_DATASET_ID,
    MIMII_MACHINE_TYPES,
    get_mimii_development_configuration,
    get_mimii_section_configuration,
    iter_mimii_development_section_scopes,
    mimii_expected_train_domain_counts,
)
from industrial_phm.experiments.mimii_development import (
    MIMII_DEVELOPMENT_AVAILABLE_CAPABILITIES,
    MIMII_DEVELOPMENT_EVIDENCE_CLASS,
    MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
    MIMII_DEVELOPMENT_RESULT_SCHEMA_ID,
    MIMII_DEVELOPMENT_UNSUPPORTED_CAPABILITIES,
)
from industrial_phm.experiments.result_inspection_support import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    InspectionFact,
    InspectionStage,
    _boolean,
    _capability_stage,
    _expect_close,
    _expect_equal,
    _integer,
    _mapping,
    _mapping_field,
    _number,
    _number_sequence,
    _positive_int,
    _provenance_stage,
    _revision,
    _sequence,
    _text,
    _text_sequence,
)
from industrial_phm.features import (
    audio_logmel_feature_names,
    audio_logmel_representation_spec,
)

_SCORE_SEMANTICS = "higher-is-more-anomalous"


def _clip_level_sequence_stage() -> InspectionStage:
    return InspectionStage(
        "Sequence Construction",
        "not applicable",
        (
            InspectionFact(
                "Reason",
                "model consumes one fixed feature vector per audio clip",
            ),
        ),
    )


def inspect_mimii_development(
    root: Mapping[str, object],
    path: Path,
) -> ExperimentInspection:
    config = get_mimii_development_configuration()
    provenance = _mapping_field(root, "provenance", "result root")
    expected_identity = (
        ("protocol_id", MIMII_DEVELOPMENT_PROTOCOL_ID),
        ("configuration_id", MIMII_DEVELOPMENT_CONFIGURATION_ID),
        ("dataset_id", MIMII_DUE_DATASET_ID),
        ("split_id", MIMII_DEVELOPMENT_SPLIT_ID),
        ("fold_id", MIMII_DEVELOPMENT_FOLD_ID),
        ("evidence_class", MIMII_DEVELOPMENT_EVIDENCE_CLASS),
    )
    for field_name, expected in expected_identity:
        _expect_equal(
            _text(provenance, field_name, "provenance"),
            expected,
            f"provenance.{field_name}",
        )
    declared_revision = _revision(provenance, "code_revision", "provenance")

    source_scope = _mapping_field(root, "source_scope", "result root")
    source_record = get_dataset(MIMII_DUE_DATASET_ID)
    if source_record.citation_doi is None:
        raise ExperimentResultInspectionError(
            "packaged MIMII DUE dataset manifest must declare citation_doi"
        )
    dataset_record = _mapping_field(source_scope, "dataset_record", "source_scope")
    expected_source_record = (
        ("version", source_record.version),
        ("provider", source_record.provider),
        ("source_url", source_record.source_url),
        ("citation_doi", source_record.citation_doi),
        ("license", source_record.license_name),
    )
    for field_name, expected_record_value in expected_source_record:
        _expect_equal(
            _text(dataset_record, field_name, "source_scope.dataset_record"),
            expected_record_value,
            f"source_scope.dataset_record.{field_name}",
        )
    verified_source_count = _positive_int(
        source_scope,
        "verified_source_clip_count",
        "source_scope",
    )
    _expect_equal(
        _text(source_scope, "source_group", "source_scope"),
        "dev",
        "source_scope.source_group",
    )
    machine_types = _text_sequence(source_scope, "machine_types", "source_scope")
    sections = _text_sequence(source_scope, "sections", "source_scope")
    train_domains = _text_sequence(source_scope, "train_domains", "source_scope")
    scoring_domains = _text_sequence(source_scope, "scoring_domains", "source_scope")
    excluded = _text_sequence(source_scope, "excluded", "source_scope")
    _expect_equal(machine_types, MIMII_MACHINE_TYPES, "source_scope.machine_types")
    _expect_equal(sections, MIMII_DEVELOPMENT_SECTIONS, "source_scope.sections")
    _expect_equal(train_domains, ("source", "target"), "source_scope.train_domains")
    _expect_equal(scoring_domains, ("source", "target"), "source_scope.scoring_domains")
    _expect_equal(
        excluded,
        (
            "eval:sections-03-05",
            "development-test-labels-from-model-fit-and-scoring",
        ),
        "source_scope.excluded",
    )

    representation = _mapping_field(root, "representation", "result root")
    selected_features = _text_sequence(
        representation,
        "selected_features",
        "representation",
    )
    expected_features = audio_logmel_feature_names()
    _expect_equal(selected_features, expected_features, "representation.selected_features")
    _expect_equal(
        _positive_int(
            representation,
            "selected_feature_count",
            "representation",
        ),
        len(expected_features),
        "representation.selected_feature_count",
    )
    _expect_equal(
        _text(representation, "feature_set_id", "representation"),
        config.feature_set_id,
        "representation.feature_set_id",
    )
    spec = audio_logmel_representation_spec()
    representation_text = (
        ("window", spec.window),
        ("padding", spec.padding),
        ("power_normalization", spec.power_normalization),
        ("mel_scale", spec.mel_scale),
        ("mel_filter_normalization", spec.mel_filter_normalization),
        ("clip_aggregation", spec.clip_aggregation),
    )
    for field_name, expected_text in representation_text:
        _expect_equal(
            _text(representation, field_name, "representation"),
            expected_text,
            f"representation.{field_name}",
        )
    representation_int = (
        ("sample_count", spec.sample_count),
        ("frame_length_samples", spec.frame_length_samples),
        ("hop_length_samples", spec.hop_length_samples),
        ("fft_size", spec.fft_size),
        ("mel_band_count", spec.mel_band_count),
        ("frame_count", spec.frame_count),
        ("feature_count", spec.feature_count),
    )
    for field_name, expected_int in representation_int:
        _expect_equal(
            _positive_int(representation, field_name, "representation"),
            expected_int,
            f"representation.{field_name}",
        )
    representation_number = (
        ("sample_rate_hz", spec.sample_rate_hz),
        ("pcm_full_scale_divisor", spec.pcm_full_scale_divisor),
        ("minimum_frequency_hz", spec.minimum_frequency_hz),
        ("maximum_frequency_hz", spec.maximum_frequency_hz),
        ("log_floor", spec.log_floor),
    )
    for field_name, expected_number in representation_number:
        _expect_close(
            _number(representation, field_name, "representation"),
            expected_number,
            f"representation.{field_name}",
        )
    _expect_equal(
        _boolean(representation, "centering", "representation"),
        spec.centering,
        "representation.centering",
    )

    preprocessing = _mapping_field(root, "preprocessing", "result root")
    _expect_equal(
        _text(preprocessing, "fit_partition", "preprocessing"),
        config.fit_partition.value,
        "preprocessing.fit_partition",
    )
    _expect_equal(
        _text(preprocessing, "scaling_strategy", "preprocessing"),
        config.scaling_strategy.value,
        "preprocessing.scaling_strategy",
    )
    _expect_equal(
        _text(preprocessing, "fit_scope", "preprocessing"),
        "per-machine-section-complete-normal-train",
        "preprocessing.fit_scope",
    )

    model = _mapping_field(root, "model", "result root")
    model_text = (
        ("model_family", config.model_family.value),
        ("reference_strategy", config.reference_strategy.value),
        ("sampling_policy_id", config.sampling_policy_id),
        ("score_semantics", _SCORE_SEMANTICS),
        ("model_unit", "machine-type-x-section"),
    )
    for field_name, expected in model_text:
        _expect_equal(
            _text(model, field_name, "model"),
            expected,
            f"model.{field_name}",
        )
    _expect_equal(
        _integer(model, "random_seed", "model"),
        config.random_seed,
        "model.random_seed",
    )
    parameters = _mapping_field(model, "parameters", "model")
    _expect_equal(dict(parameters), dict(config.model_parameters), "model.parameters")

    raw_sections = _sequence(root, "section_models", "result root")
    expected_scopes = iter_mimii_development_section_scopes()
    _expect_equal(len(raw_sections), len(expected_scopes), "section_models count")

    total_source_train = 0
    total_target_train = 0
    total_source_scoring = 0
    total_target_scoring = 0
    evaluations: dict[tuple[str, str, str], tuple[float, float]] = {}

    for index, (raw_section, scope) in enumerate(zip(raw_sections, expected_scopes, strict=True)):
        context = f"section_models[{index}]"
        section = _mapping(raw_section, context)
        _expect_equal(
            _text(section, "machine_type", context),
            scope.machine_type,
            f"{context}.machine_type",
        )
        _expect_equal(
            _text(section, "section", context),
            scope.section,
            f"{context}.section",
        )
        section_config = get_mimii_section_configuration(
            scope.machine_type,
            scope.section,
        )
        _expect_equal(
            _text(section, "experiment_id", context),
            section_config.experiment_id,
            f"{context}.experiment_id",
        )

        population = _mapping_field(section, "population_flow", context)
        source_train = _positive_int(
            population,
            "source_train_clip_count",
            f"{context}.population_flow",
        )
        target_train = _positive_int(
            population,
            "target_train_clip_count",
            f"{context}.population_flow",
        )
        expected_source_train, expected_target_train = mimii_expected_train_domain_counts(
            scope.machine_type,
            scope.section,
        )
        _expect_equal(
            source_train,
            expected_source_train,
            f"{context}.population_flow.source_train_clip_count",
        )
        _expect_equal(
            target_train,
            expected_target_train,
            f"{context}.population_flow.target_train_clip_count",
        )
        complete_train = source_train + target_train
        for field_name in (
            "preprocessing_fit_clip_count",
            "reference_clip_count",
            "model_fit_clip_count",
        ):
            _expect_equal(
                _positive_int(
                    population,
                    field_name,
                    f"{context}.population_flow",
                ),
                complete_train,
                f"{context}.population_flow.{field_name}",
            )
        source_scoring = _positive_int(
            population,
            "source_scoring_clip_count",
            f"{context}.population_flow",
        )
        target_scoring = _positive_int(
            population,
            "target_scoring_clip_count",
            f"{context}.population_flow",
        )
        total_source_train += source_train
        total_target_train += target_train
        total_source_scoring += source_scoring
        total_target_scoring += target_scoring

        state = _mapping_field(section, "preprocessing_state", context)
        fitted_center = _number_sequence(
            state,
            "fitted_center",
            f"{context}.preprocessing_state",
        )
        fitted_scale = _number_sequence(
            state,
            "fitted_scale",
            f"{context}.preprocessing_state",
        )
        zero_iqr_features = _text_sequence(
            state,
            "zero_iqr_features",
            f"{context}.preprocessing_state",
        )
        _expect_equal(
            len(fitted_center),
            len(expected_features),
            f"{context}.preprocessing_state.fitted_center width",
        )
        _expect_equal(
            len(fitted_scale),
            len(expected_features),
            f"{context}.preprocessing_state.fitted_scale width",
        )
        if any(value <= 0.0 for value in fitted_scale):
            raise ExperimentResultInspectionError(
                f"{context}.preprocessing_state.fitted_scale must be positive"
            )
        unknown_zero_iqr = sorted(set(zero_iqr_features) - set(expected_features))
        if unknown_zero_iqr:
            raise ExperimentResultInspectionError(
                f"{context}.preprocessing_state.zero_iqr_features contains "
                f"unknown feature(s): {unknown_zero_iqr}"
            )

        section_evaluation = _mapping_field(section, "evaluation", context)
        for domain, expected_count in (
            ("source", source_scoring),
            ("target", target_scoring),
        ):
            evaluation = _mapping_field(
                section_evaluation,
                domain,
                f"{context}.evaluation",
            )
            evaluations[(scope.machine_type, scope.section, domain)] = (
                *_mimii_evaluation_metrics(
                    evaluation,
                    context=f"{context}.evaluation.{domain}",
                    expected_observation_count=expected_count,
                ),
            )

    evaluation = _mapping_field(root, "evaluation", "result root")
    _expect_equal(
        _text(evaluation, "label_join", "evaluation"),
        "source-file-identity-at-evaluator-edge",
        "evaluation.label_join",
    )
    _expect_equal(
        _text(evaluation, "stratum_unit", "evaluation"),
        "machine-type-x-section-x-domain",
        "evaluation.stratum_unit",
    )
    _expect_equal(
        _text_sequence(evaluation, "metrics", "evaluation"),
        (
            "roc-auc",
            "standardized-partial-roc-auc:max-fpr=0.1",
        ),
        "evaluation.metrics",
    )
    _expect_close(
        _number(evaluation, "max_false_positive_rate", "evaluation"),
        MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
        "evaluation.max_false_positive_rate",
    )
    _expect_equal(
        _text(evaluation, "aggregation", "evaluation"),
        "harmonic-mean-with-zero-preserved",
        "evaluation.aggregation",
    )

    machine_summaries = _sequence(evaluation, "machine_summaries", "evaluation")
    _expect_equal(
        len(machine_summaries),
        len(MIMII_MACHINE_TYPES),
        "evaluation.machine_summaries count",
    )
    for index, machine_type in enumerate(MIMII_MACHINE_TYPES):
        machine_values = tuple(
            evaluations[(machine_type, section, domain)]
            for section in MIMII_DEVELOPMENT_SECTIONS
            for domain in ("source", "target")
        )
        _validate_mimii_aggregate(
            _mapping(
                machine_summaries[index],
                f"evaluation.machine_summaries[{index}]",
            ),
            context=f"evaluation.machine_summaries[{index}]",
            expected_scope=f"machine:{machine_type}",
            expected_values=machine_values,
        )

    domain_summaries = _sequence(evaluation, "domain_summaries", "evaluation")
    _expect_equal(len(domain_summaries), 2, "evaluation.domain_summaries count")
    domain_summary_values: dict[str, tuple[float, float]] = {}
    for index, domain in enumerate(("source", "target")):
        domain_values = tuple(
            evaluations[(machine_type, section, domain)]
            for machine_type in MIMII_MACHINE_TYPES
            for section in MIMII_DEVELOPMENT_SECTIONS
        )
        domain_summary_values[domain] = _validate_mimii_aggregate(
            _mapping(
                domain_summaries[index],
                f"evaluation.domain_summaries[{index}]",
            ),
            context=f"evaluation.domain_summaries[{index}]",
            expected_scope=f"domain:{domain}",
            expected_values=domain_values,
        )

    all_values = tuple(
        evaluations[(machine_type, section, domain)]
        for machine_type in MIMII_MACHINE_TYPES
        for section in MIMII_DEVELOPMENT_SECTIONS
        for domain in ("source", "target")
    )
    overall_values = _validate_mimii_aggregate(
        _mapping_field(evaluation, "overall_summary", "evaluation"),
        context="evaluation.overall_summary",
        expected_scope="mimii-only:all-strata",
        expected_values=all_values,
    )
    expected_combined = harmonic_mean_unit_interval(
        tuple(metric for pair in all_values for metric in pair)
    )
    combined = _number(
        evaluation,
        "mimii_domain_shift_summary",
        "evaluation",
    )
    _expect_close(
        combined,
        expected_combined,
        "evaluation.mimii_domain_shift_summary",
    )
    _expect_equal(
        _boolean(evaluation, "dcase_official_score", "evaluation"),
        False,
        "evaluation.dcase_official_score",
    )

    capability = _mapping_field(root, "capability", "result root")
    available = _text_sequence(capability, "available", "capability")
    unsupported = _text_sequence(capability, "unsupported", "capability")
    _expect_equal(
        available,
        MIMII_DEVELOPMENT_AVAILABLE_CAPABILITIES,
        "capability.available",
    )
    _expect_equal(
        unsupported,
        MIMII_DEVELOPMENT_UNSUPPORTED_CAPABILITIES,
        "capability.unsupported",
    )

    section_model_count = len(expected_scopes)
    train_total = total_source_train + total_target_train
    scoring_total = total_source_scoring + total_target_scoring
    return ExperimentInspection(
        schema_id=MIMII_DEVELOPMENT_RESULT_SCHEMA_ID,
        status="completed",
        stages=(
            InspectionStage(
                "Source",
                "completed",
                (
                    InspectionFact("Dataset", MIMII_DUE_DATASET_ID),
                    InspectionFact("Dataset version", source_record.version),
                    InspectionFact("Source provider", source_record.provider),
                    InspectionFact("Source URL", source_record.source_url),
                    InspectionFact("Citation DOI", source_record.citation_doi),
                    InspectionFact("License", source_record.license_name),
                    InspectionFact(
                        "Verified source profile",
                        f"{verified_source_count} WAV clips",
                    ),
                    InspectionFact("Source group", "dev"),
                    InspectionFact("Machine types", ", ".join(machine_types)),
                    InspectionFact("Sections", ", ".join(sections)),
                    InspectionFact("Excluded", ", ".join(excluded)),
                ),
            ),
            InspectionStage(
                "Canonical",
                "completed",
                (
                    InspectionFact("Channels", "pcm_amplitude"),
                    InspectionFact("Sampling rate", f"{spec.sample_rate_hz:g} Hz"),
                    InspectionFact(
                        "Cardinality",
                        "1 WAV clip -> 1 mono 10-second canonical waveform",
                    ),
                ),
            ),
            InspectionStage(
                "Feature",
                "completed",
                (
                    InspectionFact("Feature set", config.feature_set_id),
                    InspectionFact("Selected feature count", len(expected_features)),
                    InspectionFact(
                        "Representation",
                        f"{spec.mel_band_count} HTK mel bands / frame mean+population-std",
                    ),
                ),
            ),
            InspectionStage(
                "Preprocessing",
                "completed",
                (
                    InspectionFact("Fit scope", "per machine type x section complete normal train"),
                    InspectionFact("Scaling", config.scaling_strategy.value),
                    InspectionFact("Fitted states", section_model_count),
                ),
            ),
            InspectionStage(
                "Reference",
                "completed",
                (
                    InspectionFact("Strategy", config.reference_strategy.value),
                    InspectionFact("Eligible train clips", train_total),
                ),
            ),
            _clip_level_sequence_stage(),
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact("Section models", section_model_count),
                    InspectionFact("Source train clips", total_source_train),
                    InspectionFact("Target train clips", total_target_train),
                    InspectionFact("Model-fit clips", train_total),
                    InspectionFact("Source scoring clips", total_source_scoring),
                    InspectionFact("Target scoring clips", total_target_scoring),
                    InspectionFact("Total scoring clips", scoring_total),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    InspectionFact("Family", config.model_family.value),
                    InspectionFact("Model unit", "machine-type-x-section"),
                    InspectionFact("Parameters", _format_parameters(config.model_parameters)),
                    InspectionFact("Random seed", config.random_seed),
                    InspectionFact("Score semantics", _SCORE_SEMANTICS),
                ),
            ),
            InspectionStage(
                "Scoring",
                "completed",
                (
                    InspectionFact("Scope", "dev source_test + target_test"),
                    InspectionFact("Scored clips", scoring_total),
                    InspectionFact("Label access", "evaluator edge only"),
                ),
            ),
            InspectionStage(
                "Evaluation",
                "completed",
                (
                    InspectionFact("Evidence class", MIMII_DEVELOPMENT_EVIDENCE_CLASS),
                    InspectionFact("Strata", len(all_values)),
                    InspectionFact(
                        "Metrics",
                        "roc-auc, standardized-partial-roc-auc:max-fpr=0.1",
                    ),
                    InspectionFact("Aggregation", "harmonic-mean-with-zero-preserved"),
                    InspectionFact(
                        "Source AUC harmonic mean",
                        f"{domain_summary_values['source'][0]:.6g}",
                    ),
                    InspectionFact(
                        "Source pAUC harmonic mean",
                        f"{domain_summary_values['source'][1]:.6g}",
                    ),
                    InspectionFact(
                        "Target AUC harmonic mean",
                        f"{domain_summary_values['target'][0]:.6g}",
                    ),
                    InspectionFact(
                        "Target pAUC harmonic mean",
                        f"{domain_summary_values['target'][1]:.6g}",
                    ),
                    InspectionFact("Overall AUC harmonic mean", f"{overall_values[0]:.6g}"),
                    InspectionFact(
                        "Overall pAUC harmonic mean",
                        f"{overall_values[1]:.6g}",
                    ),
                    InspectionFact("MIMII domain-shift summary", f"{combined:.6g}"),
                    InspectionFact("DCASE official score", "false"),
                    InspectionFact("Selection or threshold calibration", "none"),
                ),
                warnings=(
                    "Development evidence on sections 00-02; sections 03-05 external "
                    "evaluation is not included.",
                    "Ranking metrics do not create thresholded state, diagnosis, health "
                    "indicator, maintenance priority, or RUL.",
                ),
            ),
            _capability_stage(available, unsupported),
            _provenance_stage(
                config,
                declared_revision,
                path,
                evidence_facts=(
                    InspectionFact("Protocol", MIMII_DEVELOPMENT_PROTOCOL_ID),
                    InspectionFact("Evidence class", MIMII_DEVELOPMENT_EVIDENCE_CLASS),
                    InspectionFact("Section models", section_model_count),
                ),
            ),
        ),
    )


def _mimii_evaluation_metrics(
    values: Mapping[str, object],
    *,
    context: str,
    expected_observation_count: int,
) -> tuple[float, float]:
    observation_count = _positive_int(values, "observation_count", context)
    _expect_equal(
        observation_count,
        expected_observation_count,
        f"{context}.observation_count",
    )
    normal_count = _positive_int(values, "normal_count", context)
    anomaly_count = _positive_int(values, "anomaly_count", context)
    _expect_equal(
        normal_count + anomaly_count,
        observation_count,
        f"{context} normal/anomaly count",
    )
    roc_auc = _number(values, "roc_auc", context)
    partial_roc_auc = _number(values, "partial_roc_auc", context)
    for field_name, value in (
        ("roc_auc", roc_auc),
        ("partial_roc_auc", partial_roc_auc),
    ):
        if not 0.0 <= value <= 1.0:
            raise ExperimentResultInspectionError(f"{context}.{field_name} must be in [0, 1]")
    _expect_close(
        _number(values, "max_false_positive_rate", context),
        MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
        f"{context}.max_false_positive_rate",
    )
    return roc_auc, partial_roc_auc


def _validate_mimii_aggregate(
    values: Mapping[str, object],
    *,
    context: str,
    expected_scope: str,
    expected_values: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    _expect_equal(
        _text(values, "scope_id", context),
        expected_scope,
        f"{context}.scope_id",
    )
    _expect_equal(
        _positive_int(values, "stratum_count", context),
        len(expected_values),
        f"{context}.stratum_count",
    )
    roc_auc = _number(values, "roc_auc_harmonic_mean", context)
    partial_roc_auc = _number(
        values,
        "partial_roc_auc_harmonic_mean",
        context,
    )
    _expect_close(
        roc_auc,
        harmonic_mean_unit_interval(tuple(pair[0] for pair in expected_values)),
        f"{context}.roc_auc_harmonic_mean",
    )
    _expect_close(
        partial_roc_auc,
        harmonic_mean_unit_interval(tuple(pair[1] for pair in expected_values)),
        f"{context}.partial_roc_auc_harmonic_mean",
    )
    return roc_auc, partial_roc_auc


def _format_parameters(parameters: Mapping[str, ExperimentParameter]) -> str:
    return ", ".join(f"{name}={value!r}" for name, value in sorted(parameters.items()))
