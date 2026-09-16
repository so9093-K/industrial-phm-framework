"""Reproducible experiment inputs and protocol contracts."""

from industrial_phm.experiments.xjtu import (
    XjtuExperimentProtocolError,
    XjtuSplitFold,
    XjtuSplitManifest,
    get_xjtu_reference_split,
)
from industrial_phm.experiments.xjtu_characterization import (
    XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
    XjtuCharacterizationArtifacts,
    XjtuFeatureCharacterizationError,
    characterize_xjtu_source,
    write_xjtu_characterization_artifacts,
)

__all__ = [
    "XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID",
    "XjtuCharacterizationArtifacts",
    "XjtuExperimentProtocolError",
    "XjtuFeatureCharacterizationError",
    "XjtuSplitFold",
    "XjtuSplitManifest",
    "characterize_xjtu_source",
    "get_xjtu_reference_split",
    "write_xjtu_characterization_artifacts",
]
