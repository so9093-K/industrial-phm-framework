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
        "# PHM 분석 보고서",
        "",
        "## 분석 대상",
        "",
        f"- 설비: `{asset.asset_id}`",
        f"- 데이터셋: `{analysis.identity.dataset_id}`",
        "",
        "## 이상 변화 요약",
        "",
        f"- 분석 구간 수: {asset.score_window_count}",
        f"- 시간 순서와 이상 점수의 상관계수(Spearman rho): "
        f"{asset.acquisition_order_spearman_rho:.6g}",
        "",
        "### 점수가 높았던 관측값",
        "",
        "| Acquisition | 원본 관측값 | 점수 |",
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
            "### 특징 잔차 상위 항목",
            "",
            "| 특징 | 평균 제곱 잔차 |",
            "| --- | ---: |",
        )
    )
    lines.extend(f"| `{name}` | {value:.6g} |" for name, value in residuals)

    if prognostics is not None:
        _append_prognostics(lines, analysis, prognostics, asset.asset_id)

    lines.extend(
        (
            "",
            "## 기술 정보",
            "",
            f"- Split: `{analysis.identity.split_id}` / `{analysis.identity.fold_id}`",
            f"- Evidence class: `{analysis.evidence_class}`",
            f"- Code revision: `{analysis.identity.code_revision}`",
            f"- Artifact: `{analysis.artifact_path}`",
            f"- Score semantics: `{anomaly.score_semantics_id}`",
            f"- Direction: `{anomaly.score_direction}`",
            f"- Late-vs-middle rank probability: "
            f"{asset.late_vs_middle_rank_probability:.6g}",
            "",
            "### 분석 결과에 기록된 기능 범위",
            "",
            "사용 가능한 항목:",
            "",
            *[f"- {item}" for item in analysis.available_capabilities],
            "",
            "지원하지 않거나 검증되지 않은 항목:",
            "",
            *[f"- {item}" for item in analysis.unsupported_capabilities],
        )
    )

    _append_inspection_warnings(lines, analysis, heading="이상 분석 기술 경고")
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
    lines.extend(("", "## RUL 분석 결과", ""))
    if not compatibility.compatible:
        lines.append(
            "현재 이상 분석 결과와 RUL 분석 결과의 데이터 범위가 맞지 않아 "
            "같은 보고서의 결과로 표시하지 않았습니다."
        )
        lines.extend(f"- {reason}" for reason in compatibility.reasons)
        return

    try:
        summary = summarize_prognostics_for_asset(prognostics, asset_id)
    except AnalysisViewError as error:
        raise AnalysisReportError(str(error)) from error

    lines.extend(
        (
            "저장된 RUL 모델 결과를 같은 설비 기준으로 비교합니다. "
            "이 표의 값은 실시간 설비 예측이 아니라 저장된 분석 결과입니다.",
            "",
            "| 방법 | 마지막 기록 시점 RUL 예측 | 기준 acquisition | 검증 MAE | Signed error |",
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

    if summary.primary_method_id is None:
        lines.extend(("", "현재 이 보고서에서 대표 RUL 모델을 별도로 지정하지 않습니다."))
    else:
        lines.extend(("", f"기록된 대표 모델: `{summary.primary_method_id}`"))

    lines.extend(
        (
            "",
            "### RUL 기술 정보",
            "",
            f"- Relationship: `{compatibility.relationship}`",
            f"- Evidence class: `{summary.evidence_class}`",
            f"- Code revision: `{prognostics.identity.code_revision}`",
            f"- Artifact: `{summary.artifact_path}`",
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
            "이상 분석 artifact와 RUL artifact는 선언된 dataset/split/population 범위가 "
            "맞는지 확인해 함께 표시하지만, exact source byte identity는 현재 기록하지 않습니다.",
        )
    )
    _append_inspection_warnings(lines, prognostics, heading="RUL 분석 기술 경고")


def _append_inspection_warnings(
    lines: list[str],
    analysis: AnalysisView,
    *,
    heading: str,
) -> None:
    warnings = tuple(warning for stage in analysis.inspection.stages for warning in stage.warnings)
    if not warnings:
        return
    lines.extend(("", f"### {heading}", ""))
    lines.extend(f"- {warning}" for warning in warnings)
