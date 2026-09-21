"""Compatibility checks for composing independently validated analysis evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from industrial_phm.analysis.view import AnalysisView

EvidenceRelationship = Literal[
    "compatible-separate-artifacts",
    "compatible-separate-revision",
    "incompatible",
]


@dataclass(frozen=True, slots=True)
class AnalysisEvidenceCompatibility:
    """Whether two validated evidence artifacts can safely share one analysis surface."""

    compatible: bool
    relationship: EvidenceRelationship
    same_code_revision: bool
    source_identity_verified: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def compare_analysis_evidence(
    primary: AnalysisView,
    attached: AnalysisView,
) -> AnalysisEvidenceCompatibility:
    """Compare artifact-owned identity without treating separate runs as one execution."""
    left = primary.identity
    right = attached.identity
    reasons: list[str] = []

    comparable_fields = (
        ("dataset_id", left.dataset_id, right.dataset_id),
        ("split_id", left.split_id, right.split_id),
        ("fold_id", left.fold_id, right.fold_id),
        (
            "evaluation_partition",
            left.evaluation_partition,
            right.evaluation_partition,
        ),
        ("train_asset_ids", left.train_asset_ids, right.train_asset_ids),
        (
            "evaluation_asset_ids",
            left.evaluation_asset_ids,
            right.evaluation_asset_ids,
        ),
        ("excluded_scope", left.excluded_scope, right.excluded_scope),
        (
            "verified_source_acquisition_count",
            left.verified_source_acquisition_count,
            right.verified_source_acquisition_count,
        ),
    )
    for field_name, primary_value, attached_value in comparable_fields:
        if primary_value != attached_value:
            reasons.append(
                f"{field_name} differs: primary={primary_value!r}, attached={attached_value!r}"
            )

    same_revision = left.code_revision == right.code_revision
    warnings: list[str] = [
        (
            "source byte identity is not recorded in these artifacts; compatibility only "
            "establishes matching declared dataset/split/population scope"
        )
    ]
    if primary.artifact_path != attached.artifact_path:
        warnings.append(
            "evidence comes from a separate artifact and must not be presented as one execution"
        )
    if not same_revision:
        warnings.append(
            "code revision differs between primary and attached evidence"
        )

    compatible = not reasons
    if not compatible:
        relationship: EvidenceRelationship = "incompatible"
    elif same_revision:
        relationship = "compatible-separate-artifacts"
    else:
        relationship = "compatible-separate-revision"

    return AnalysisEvidenceCompatibility(
        compatible=compatible,
        relationship=relationship,
        same_code_revision=same_revision,
        source_identity_verified=False,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )
