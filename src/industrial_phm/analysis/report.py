"""Deterministic Markdown export for validated PHM analysis read models."""

from __future__ import annotations

from pathlib import Path

from industrial_phm.analysis.view import AnalysisView, AnalysisViewError


class AnalysisReportError(ValueError):
    """Raised when a deterministic analysis report cannot be rendered safely."""


def render_analysis_report_markdown(analysis: AnalysisView, asset_id: str) -> str:
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

    lines.extend(
        (
            "",
            "## 기술 정보",
            "",
            f"- 데이터 분할: `{analysis.identity.split_id}` / `{analysis.identity.fold_id}`",
            f"- 결과 분류: `{analysis.evidence_class}`",
            f"- 코드 버전(Git revision): `{analysis.identity.code_revision}`",
            f"- 결과 파일: `{analysis.artifact_path}`",
            f"- 점수 정의: `{anomaly.score_semantics_id}`",
            f"- 점수 방향: `{anomaly.score_direction}`",
            f"- 후기 대비 중기 순위 확률: {asset.late_vs_middle_rank_probability:.6g}",
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
    analysis: AnalysisView, asset_id: str, output_path: Path
) -> None:
    """Write deterministic Markdown to an explicit output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_analysis_report_markdown(analysis, asset_id), encoding="utf-8")


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
