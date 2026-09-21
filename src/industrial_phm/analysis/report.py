"""Deterministic Markdown export for validated PHM analysis read models."""

from __future__ import annotations

from pathlib import Path

from industrial_phm.analysis.compatibility import compare_analysis_evidence
from industrial_phm.analysis.prognostics_summary import summarize_prognostics_for_asset
from industrial_phm.analysis.view import AnalysisView, AnalysisViewError


class AnalysisReportError(ValueError):
    """Raised when a deterministic analysis report cannot be rendered safely."""


def render_analysis_report_markdown(
    analysis: AnalysisView,
    asset_id: str,
    *,
    prognostics: AnalysisView | None = None,
) -> str:
    """Render one deterministic report from validated read models without recomputation."""
    try:
        anomaly = analysis.require_anomaly_evidence()
        asset = anomaly.asset(asset_id)
    except AnalysisViewError as error:
        raise AnalysisReportError(str(error)) from error

    lines = [
        "# PHM Analysis Report",
        "",
        "## Scope",
        "",
        f"- Asset: `{asset.asset_id}`",
        f"- Dataset: `{analysis.identity.dataset_id}`",
        f"- Split: `{analysis.identity.split_id}` / `{analysis.identity.fold_id}`",
        f"- Evidence class: `{analysis.evidence_class}`",
        f"- Code revision: `{analysis.identity.code_revision}`",
        f"- Artifact: `{analysis.artifact_path}`",
        "",
        "This report renders validated evidence already present in the read model. "
        "It does not refit a model, recompute PHM metrics, create a diagnosis, or infer RUL.",
        "",
        "## Anomaly evidence",
        "",
        f"- Score semantics: `{anomaly.score_semantics_id}`",
        f"- Direction: `{anomaly.score_direction}`",
        f"- Recorded scored windows: {asset.score_window_count}",
        f"- Acquisition-order Spearman rho: {asset.acquisition_order_spearman_rho:.6g}",
        f"- Late-vs-middle rank probability: {asset.late_vs_middle_rank_probability:.6g}",
        "",
        "### Highest recorded scores",
        "",
        "| Acquisition | Source observation | Score |",
        "| ---: | --- | ---: |",
    ]
    highest = sorted(asset.observations, key=lambda item: item.score, reverse=True)[:5]
    lines.extend(
        f"| {item.acquisition_index} | `{item.source_observation_id}` | {item.score:.6g} |"
        for item in highest
    )

    residuals = sorted(
        zip(anomaly.feature_names, asset.mean_feature_residuals, strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )[:5]
    lines.extend(
        (
            "",
            "### Highest recorded mean feature residuals",
            "",
            "| Feature | Mean squared residual |",
            "| --- | ---: |",
        )
    )
    lines.extend(f"| `{name}` | {value:.6g} |" for name, value in residuals)

    lines.extend(
        (
            "",
            "## Capability boundary",
            "",
            "Available in the anomaly artifact:",
            "",
            *[f"- {item}" for item in analysis.available_capabilities],
            "",
            "Unsupported or not validated in the anomaly artifact:",
            "",
            *[f"- {item}" for item in analysis.unsupported_capabilities],
        )
    )

    _append_inspection_warnings(lines, analysis, heading="Anomaly evidence warnings")

    if prognostics is not None:
        _append_prognostics(lines, analysis, prognostics, asset.asset_id)

    return "\n".join(lines).rstrip() + "\n"


def write_analysis_report_markdown(
    analysis: AnalysisView,
    asset_id: str,
    output_path: Path,
    *,
    prognostics: AnalysisView | None = None,
) -> None:
    """Write deterministic Markdown to an explicit output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_analysis_report_markdown(
            analysis,
            asset_id,
            prognostics=prognostics,
        ),
        encoding="utf-8",
    )


def _append_prognostics(
    lines: list[str],
    analysis: AnalysisView,
    prognostics: AnalysisView,
    asset_id: str,
) -> None:
    compatibility = compare_analysis_evidence(analysis, prognostics)
    lines.extend(("", "## Attached prognostics evidence", ""))
    if not compatibility.compatible:
        lines.append(
            "The attached prognostics artifact was not included because its declared "
            "population/protocol scope is incompatible with the anomaly artifact."
        )
        lines.extend(f"- {reason}" for reason in compatibility.reasons)
        return

    try:
        summary = summarize_prognostics_for_asset(prognostics, asset_id)
    except AnalysisViewError as error:
        raise AnalysisReportError(str(error)) from error

    lines.extend(
        (
            "This is separate retrospective evidence, not another stage of the anomaly "
            "artifact execution.",
            "",
            f"- Relationship: `{compatibility.relationship}`",
            f"- Prognostics evidence class: `{summary.evidence_class}`",
            f"- Prognostics code revision: `{prognostics.identity.code_revision}`",
            f"- Prognostics artifact: `{summary.artifact_path}`",
            f"- Target: `{summary.target_definition_id}`",
            f"- Unit: `{summary.target_unit}`",
            f"- Formula: `{summary.target_formula}`",
            f"- Endpoint semantics: `{summary.endpoint_semantics}`",
            f"- Target clipped: {str(summary.target_is_clipped).lower()}",
            f"- Support: {summary.support_definition} from acquisition "
            f"{summary.support_first_acquisition}",
            f"- Uncertainty interval available: "
            f"{str(summary.uncertainty_interval_available).lower()}",
            f"- Physical failure threshold validated: "
            f"{str(summary.physical_failure_threshold_validated).lower()}",
            "",
            "Exact source byte identity is not recorded in these artifacts; this attachment "
            "only establishes matching declared dataset/split/population scope.",
            "",
            "### Method comparison",
            "",
            "| Method | Recorded estimate | As-of acquisition | MAE | Signed error |",
            "| --- | ---: | ---: | ---: | ---: |",
        )
    )
    lines.extend(
        (
            f"| `{row.method_id}` | {row.last_recorded_remaining_useful_life:.6g} | "
            f"{row.last_recorded_acquisition_index} | {row.mean_absolute_error:.6g} | "
            f"{row.mean_signed_error:.6g} |"
        )
        for row in summary.methods
    )
    lines.extend(
        (
            "",
            "No operational primary method is asserted by this report."
            if summary.primary_method_id is None
            else f"Recorded primary method: `{summary.primary_method_id}`",
        )
    )
    _append_inspection_warnings(lines, prognostics, heading="Prognostics evidence warnings")


def _append_inspection_warnings(
    lines: list[str],
    analysis: AnalysisView,
    *,
    heading: str,
) -> None:
    warnings = tuple(
        warning
        for stage in analysis.inspection.stages
        for warning in stage.warnings
    )
    if not warnings:
        return
    lines.extend(("", f"### {heading}", ""))
    lines.extend(f"- {warning}" for warning in warnings)
