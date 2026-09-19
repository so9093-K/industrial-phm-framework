"""MIMII DUE fixed development scope and section-level experiment configurations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources

from industrial_phm.experiments.config import (
    ExperimentConfig,
    ExperimentContext,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    load_experiment_configs,
)
from industrial_phm.features import (
    AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
    audio_logmel_feature_names,
)

MIMII_DUE_DATASET_ID = "mimii-due"
MIMII_DEVELOPMENT_PROTOCOL_ID = "mimii-due-domain-shift-iforest-v1"
MIMII_DEVELOPMENT_SPLIT_ID = "mimii-due-dev-sections-00-02-v1"
MIMII_DEVELOPMENT_FOLD_ID = "fold-1"
MIMII_DEVELOPMENT_CONFIGURATION_ID = "mimii-due-iforest-domain-shift-development-v1"
MIMII_MACHINE_TYPES = ("fan", "gearbox", "pump", "slider", "valve")
MIMII_DEVELOPMENT_SECTIONS = ("00", "01", "02")
MIMII_TARGET_TRAIN_COUNT_PER_SECTION = 3

_EXPECTED_SOURCE_TRAIN_COUNT = {
    ("fan", "00"): 1_000,
    ("fan", "01"): 1_000,
    ("fan", "02"): 1_000,
    ("gearbox", "00"): 1_001,
    ("gearbox", "01"): 1_008,
    ("gearbox", "02"): 1_008,
    ("pump", "00"): 1_000,
    ("pump", "01"): 1_000,
    ("pump", "02"): 1_000,
    ("slider", "00"): 1_000,
    ("slider", "01"): 1_000,
    ("slider", "02"): 1_000,
    ("valve", "00"): 1_000,
    ("valve", "01"): 1_000,
    ("valve", "02"): 1_000,
}

_CONFIG_MANIFEST = "mimii-due-iforest-domain-shift-development-v1.toml"
_SUPPORTED_SAMPLING_POLICY_IDS = ("clip-uniform-v1",)
_EXPECTED_MODEL_PARAMETERS = {
    "n_estimators": 256,
    "max_samples": "auto",
    "contamination": "auto",
    "max_features": 1.0,
    "bootstrap": False,
}


class MimiiExperimentProtocolError(ValueError):
    """Raised when a MIMII development configuration drifts from protocol v1."""


@dataclass(frozen=True, slots=True)
class MimiiSectionScope:
    """One machine-type and section model scope inside MIMII development v1."""

    machine_type: str
    section: str

    def __post_init__(self) -> None:
        if self.machine_type not in MIMII_MACHINE_TYPES:
            raise MimiiExperimentProtocolError(
                f"unsupported MIMII machine_type: {self.machine_type!r}"
            )
        if self.section not in MIMII_DEVELOPMENT_SECTIONS:
            raise MimiiExperimentProtocolError(
                f"unsupported MIMII development section: {self.section!r}"
            )

    @property
    def asset_id(self) -> str:
        """Return the canonical source identity shared by clips in this scope."""
        return f"{self.machine_type}/section-{self.section}"

    @property
    def experiment_id(self) -> str:
        """Return the unique model experiment identity for this section scope."""
        return f"{MIMII_DEVELOPMENT_CONFIGURATION_ID}--{self.machine_type}-section-{self.section}"


def mimii_expected_train_domain_counts(
    machine_type: str,
    section: str,
) -> tuple[int, int]:
    """Return protocol-fixed source/target normal train counts for one development section."""
    scope = MimiiSectionScope(machine_type=machine_type, section=section)
    return (
        _EXPECTED_SOURCE_TRAIN_COUNT[(scope.machine_type, scope.section)],
        MIMII_TARGET_TRAIN_COUNT_PER_SECTION,
    )


def mimii_development_context() -> ExperimentContext:
    """Return the dataset-owned context for the fixed MIMII development configuration."""
    return ExperimentContext(
        dataset_id=MIMII_DUE_DATASET_ID,
        split_id=MIMII_DEVELOPMENT_SPLIT_ID,
        fold_ids=(MIMII_DEVELOPMENT_FOLD_ID,),
        feature_set_id=AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
        feature_names=audio_logmel_feature_names(),
        supported_sampling_policy_ids=_SUPPORTED_SAMPLING_POLICY_IDS,
    )


@lru_cache(maxsize=1)
def get_mimii_development_configuration() -> ExperimentConfig:
    """Return the protocol-fixed base configuration before section identity is resolved."""
    content = (
        resources.files("industrial_phm.experiments.manifests")
        .joinpath(_CONFIG_MANIFEST)
        .read_text(encoding="utf-8")
    )
    configs = load_experiment_configs(content, context=mimii_development_context())
    if len(configs) != 1:
        raise MimiiExperimentProtocolError(
            f"MIMII development manifest must contain exactly one experiment, got {len(configs)}"
        )

    config = configs[0]
    expected_axes = (
        ("experiment_id", config.experiment_id, MIMII_DEVELOPMENT_CONFIGURATION_ID),
        ("dataset_id", config.dataset_id, MIMII_DUE_DATASET_ID),
        ("split_id", config.split_id, MIMII_DEVELOPMENT_SPLIT_ID),
        ("fold_id", config.fold_id, MIMII_DEVELOPMENT_FOLD_ID),
        ("reference_strategy", config.reference_strategy, ReferenceStrategy.ALL_TRAIN_OBSERVATIONS),
        ("sampling_policy_id", config.sampling_policy_id, "clip-uniform-v1"),
        ("scaling_strategy", config.scaling_strategy, ScalingStrategy.ROBUST),
        ("model_family", config.model_family, ModelFamily.ISOLATION_FOREST),
        ("random_seed", config.random_seed, 42),
    )
    for field_name, value, expected in expected_axes:
        if value != expected:
            raise MimiiExperimentProtocolError(
                f"MIMII development {field_name} must be {expected!r}, got {value!r}"
            )

    if tuple(config.selected_features) != audio_logmel_feature_names():
        raise MimiiExperimentProtocolError(
            "MIMII development selected_features must be the full "
            "audio-logmel-statistical-v1 schema"
        )
    if dict(config.model_parameters) != _EXPECTED_MODEL_PARAMETERS:
        raise MimiiExperimentProtocolError(
            "MIMII development model parameters must match the protocol-fixed Isolation Forest"
        )
    return config


def iter_mimii_development_section_scopes() -> tuple[MimiiSectionScope, ...]:
    """Return all fifteen section-model scopes in deterministic machine-major order."""
    return tuple(
        MimiiSectionScope(machine_type=machine_type, section=section)
        for machine_type in MIMII_MACHINE_TYPES
        for section in MIMII_DEVELOPMENT_SECTIONS
    )


def get_mimii_section_configuration(
    machine_type: str,
    section: str,
) -> ExperimentConfig:
    """Resolve the shared protocol configuration into one unique section-model config."""
    scope = MimiiSectionScope(machine_type=machine_type, section=section)
    return replace(get_mimii_development_configuration(), experiment_id=scope.experiment_id)


def get_mimii_section_scope(config: ExperimentConfig) -> MimiiSectionScope:
    """Resolve and validate the section scope owned by one derived configuration."""
    for scope in iter_mimii_development_section_scopes():
        if config.experiment_id != scope.experiment_id:
            continue
        expected = get_mimii_section_configuration(scope.machine_type, scope.section)
        if config != expected:
            raise MimiiExperimentProtocolError(
                "MIMII section configuration drift for "
                f"{scope.machine_type}/section-{scope.section}"
            )
        return scope
    raise MimiiExperimentProtocolError(
        f"unknown MIMII section experiment_id: {config.experiment_id!r}"
    )
