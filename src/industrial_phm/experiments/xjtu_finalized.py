"""The single finalized XJTU fold-1 experiment configuration.

Development used two comparison manifests: four v2 candidates chosen by the frozen selection
rule, then two v3 reference hypotheses compared under the frozen decision rule. Both remain as
historical evidence. This module owns the one configuration those comparisons finalized, so
downstream holdout evaluation consumes exactly one configuration and never re-opens a grid.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from industrial_phm.experiments.config import ExperimentConfig, ReferenceStrategy
from industrial_phm.experiments.xjtu import (
    get_xjtu_isolation_forest_candidates,
    load_packaged_xjtu_experiment_configs,
)

XJTU_FINALIZED_CONFIGURATION_ID = "xjtu-sy-iforest-fold-1-finalized-v1"

_FINALIZED_MANIFEST = "xjtu-sy-iforest-fold-1-finalized-v1.toml"
_SELECTED_V2_CANDIDATE_ID = "xjtu-sy-iforest-fold-1-acquisition-uniform-full-16-identity-v2"
_ADOPTED_REFERENCE_STRATEGY = ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD
_FOLD_ID = "fold-1"

_AXES_INHERITED_FROM_SELECTED_CANDIDATE = (
    "dataset_id",
    "split_id",
    "fold_id",
    "fit_partition",
    "feature_set_id",
    "selected_features",
    "sampling_policy_id",
    "scaling_strategy",
    "model_family",
    "random_seed",
)


class XjtuFinalizedConfigurationError(ValueError):
    """Raised when the finalized configuration drifts from what development finalized."""


@lru_cache(maxsize=1)
def get_xjtu_finalized_configuration() -> ExperimentConfig:
    """Return the one configuration fold-1 development finalized.

    Loading fails unless the manifest holds exactly one experiment whose every axis matches the
    selected v2 candidate, except ``reference_strategy``, which must be the adopted alternative.
    The check runs against packaged manifests only: generated research artifacts never gate
    production code.
    """
    configs = load_packaged_xjtu_experiment_configs(_FINALIZED_MANIFEST)
    _validate_finalized_scope(configs)
    return configs[0]


def _validate_finalized_scope(configs: Sequence[ExperimentConfig]) -> None:
    if len(configs) != 1:
        raise XjtuFinalizedConfigurationError(
            "the finalized configuration manifest must hold exactly one experiment, "
            f"got {len(configs)}"
        )

    config = configs[0]
    if config.experiment_id != XJTU_FINALIZED_CONFIGURATION_ID:
        raise XjtuFinalizedConfigurationError(
            f"finalized experiment_id must be {XJTU_FINALIZED_CONFIGURATION_ID!r}, "
            f"got {config.experiment_id!r}"
        )
    if config.fold_id != _FOLD_ID:
        raise XjtuFinalizedConfigurationError(
            f"the finalized configuration is fold-1 only, got {config.fold_id!r}"
        )
    if config.reference_strategy is not _ADOPTED_REFERENCE_STRATEGY:
        raise XjtuFinalizedConfigurationError(
            "finalized reference_strategy must be the adopted "
            f"{_ADOPTED_REFERENCE_STRATEGY.value!r}, got {config.reference_strategy.value!r}"
        )

    selected = _selected_v2_candidate()
    for axis in _AXES_INHERITED_FROM_SELECTED_CANDIDATE:
        finalized_value = getattr(config, axis)
        selected_value = getattr(selected, axis)
        if axis == "selected_features":
            finalized_value = tuple(finalized_value)
            selected_value = tuple(selected_value)
        if finalized_value != selected_value:
            raise XjtuFinalizedConfigurationError(
                f"finalized {axis} must match the selected candidate "
                f"{_SELECTED_V2_CANDIDATE_ID!r}; "
                f"expected {selected_value!r}, got {finalized_value!r}"
            )
    if dict(config.model_parameters) != dict(selected.model_parameters):
        raise XjtuFinalizedConfigurationError(
            "finalized model_parameters must match the selected candidate "
            f"{_SELECTED_V2_CANDIDATE_ID!r}"
        )


def _selected_v2_candidate() -> ExperimentConfig:
    candidates = {
        candidate.experiment_id: candidate for candidate in get_xjtu_isolation_forest_candidates()
    }
    try:
        return candidates[_SELECTED_V2_CANDIDATE_ID]
    except KeyError as error:
        raise XjtuFinalizedConfigurationError(
            f"packaged candidates no longer contain {_SELECTED_V2_CANDIDATE_ID!r}"
        ) from error
