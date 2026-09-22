import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt

    from industrial_phm.analysis import (
        AnalysisReportError,
        AnalysisRunError,
        AnalysisViewError,
        compare_analysis_evidence,
        derive_early_scored_window_review_threshold,
        load_xjtu_lstm_analysis_view,
        load_xjtu_rul_analysis_view,
        run_xjtu_lstm_analysis_from_source,
        score_exceedance_intervals,
        summarize_prognostics_for_asset,
        write_analysis_report_markdown,
    )
    from industrial_phm.genai import (
        AnalysisExplanationError,
        build_analysis_explanation_context,
        build_prognostics_explanation_context,
        generate_openai_analysis_explanation,
        generate_openai_prognostics_explanation,
    )

    return (
        AnalysisExplanationError,
        AnalysisReportError,
        AnalysisRunError,
        AnalysisViewError,
        Path,
        build_analysis_explanation_context,
        build_prognostics_explanation_context,
        compare_analysis_evidence,
        derive_early_scored_window_review_threshold,
        generate_openai_analysis_explanation,
        generate_openai_prognostics_explanation,
        load_xjtu_lstm_analysis_view,
        load_xjtu_rul_analysis_view,
        mo,
        os,
        plt,
        run_xjtu_lstm_analysis_from_source,
        score_exceedance_intervals,
        summarize_prognostics_for_asset,
        write_analysis_report_markdown,
    )


@app.cell
def _(AnalysisViewError, Path, load_xjtu_lstm_analysis_view, mo, os):
    artifact_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_ANALYSIS_ARTIFACT",
            "docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json",
        )
    )
    mo.stop(
        not artifact_path.is_file(),
        mo.callout(
            f"분석 결과 파일을 찾을 수 없습니다: `{artifact_path}`",
            kind="warn",
            title="분석 결과를 열 수 없습니다",
        ),
    )

    try:
        initial_analysis = load_xjtu_lstm_analysis_view(artifact_path)
    except AnalysisViewError as error:
        mo.stop(
            True,
            mo.callout(str(error), kind="danger", title="분석 결과 검증 실패"),
        )

    return artifact_path, initial_analysis


@app.cell
def _(initial_analysis, mo):
    get_analysis, set_analysis = mo.state(initial_analysis)
    return get_analysis, set_analysis


@app.cell
def _(get_analysis):
    analysis = get_analysis()
    return (analysis,)


@app.cell
def _(analysis, mo):
    asset_selector = mo.ui.dropdown(
        options=[asset.asset_id for asset in analysis.require_anomaly_evidence().assets],
        value=analysis.require_anomaly_evidence().assets[0].asset_id,
        label="분석 대상",
    )
    view_selector = mo.ui.radio(
        options=[
            "분석 요약",
            "이상 근거",
            "RUL 분석",
            "AI 설명",
            "새 분석 실행",
            "보고서 저장",
            "상세 정보",
        ],
        value="분석 요약",
        inline=True,
        label="보기",
    )
    header = mo.md(
        """
        # PHM 분석 Explorer

        저장된 분석 결과를 JSON 파일을 직접 읽지 않고 확인할 수 있습니다.
        결과를 먼저 보고, 모델과 실행 정보는 **상세 정보**에서 확인할 수 있습니다.
        """
    )
    return asset_selector, header, view_selector


@app.cell
def _(
    analysis,
    asset_selector,
    derive_early_scored_window_review_threshold,
    score_exceedance_intervals,
):
    selected_asset = analysis.require_anomaly_evidence().asset(asset_selector.value)
    review_threshold = derive_early_scored_window_review_threshold(selected_asset)
    review_intervals = score_exceedance_intervals(selected_asset, review_threshold)
    return review_intervals, review_threshold, selected_asset


@app.cell
def _(
    analysis,
    build_analysis_explanation_context,
    os,
    selected_asset,
):
    explanation_context = build_analysis_explanation_context(
        analysis,
        selected_asset.asset_id,
    )
    explanation_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    explanation_model = os.environ.get("INDUSTRIAL_PHM_GENAI_MODEL", "").strip()
    explanation_configured = bool(explanation_api_key and explanation_model)
    return (
        explanation_api_key,
        explanation_configured,
        explanation_context,
        explanation_model,
    )


@app.cell
def _(mo):
    explanation_question = mo.ui.text_area(
        value="이 분석 결과에서 관찰된 변화와 현재 해석 가능한 범위를 설명해주세요.",
        label="이 결과에 대해 질문하기",
        rows=3,
        full_width=True,
    )
    explanation_run = mo.ui.run_button(label="AI 설명 생성", kind="success")
    explanation_scope = mo.ui.radio(
        options=["이상 분석 결과", "RUL 분석 결과"],
        value="이상 분석 결과",
        label="설명할 결과",
    )
    return explanation_question, explanation_run, explanation_scope


@app.cell
def _(
    AnalysisExplanationError,
    asset_selector,
    build_prognostics_explanation_context,
    prognostics_analysis,
    prognostics_compatibility,
    prognostics_error,
):
    if prognostics_analysis is None:
        prognostics_explanation_context = None
        prognostics_context_error = prognostics_error
    elif prognostics_compatibility is None or not prognostics_compatibility.compatible:
        prognostics_explanation_context = None
        _reasons = (
            "결과 범위 호환성을 확인할 수 없음"
            if prognostics_compatibility is None
            else "; ".join(prognostics_compatibility.reasons)
        )
        prognostics_context_error = (
            "현재 이상 분석 결과와 연결된 RUL 분석 결과의 범위가 맞지 않습니다: "
            f"{_reasons}"
        )
    else:
        try:
            prognostics_explanation_context = build_prognostics_explanation_context(
                prognostics_analysis,
                asset_selector.value,
            )
            prognostics_context_error = ""
        except AnalysisExplanationError as error:
            prognostics_explanation_context = None
            prognostics_context_error = str(error)
    return prognostics_context_error, prognostics_explanation_context


@app.cell
def _(Path, mo, os):
    analysis_source_input = mo.ui.text(
        value=os.environ.get("INDUSTRIAL_PHM_XJTU_SOURCE", ""),
        label="준비된 XJTU-SY 데이터 폴더",
        full_width=True,
    )
    analysis_output_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_ANALYSIS_OUTPUT",
            "artifacts/analysis/xjtu-lstm-analysis.json",
        )
    )
    analysis_run_button = mo.ui.run_button(label="분석 실행", kind="success")
    return analysis_output_path, analysis_run_button, analysis_source_input


@app.cell
def _(
    AnalysisRunError,
    Path,
    analysis_output_path,
    analysis_run_button,
    analysis_source_input,
    mo,
    run_xjtu_lstm_analysis_from_source,
    set_analysis,
):
    source_value = analysis_source_input.value.strip()
    source_path = Path(source_value) if source_value else None
    source_ready = source_path is not None and source_path.is_dir()

    if not analysis_run_button.value:
        if source_value and not source_ready:
            analysis_run_output = mo.callout(
                "입력한 데이터 폴더를 찾을 수 없습니다. 경로를 다시 확인해주세요.",
                kind="warn",
                title="데이터 폴더 확인 필요",
            )
        else:
            analysis_run_output = mo.callout(
                "데이터 폴더를 지정한 뒤 분석 실행을 누르세요. "
                "Git revision은 현재 clean checkout에서 자동으로 기록됩니다.",
                kind="info",
                title="분석 준비",
            )
    elif not source_value:
        analysis_run_output = mo.callout(
            "분석할 XJTU-SY 데이터 폴더를 입력해주세요.",
            kind="warn",
            title="분석을 시작하지 않았습니다",
        )
    elif not source_ready:
        analysis_run_output = mo.callout(
            "입력한 데이터 폴더를 찾을 수 없습니다. 경로를 확인해주세요.",
            kind="warn",
            title="분석을 시작하지 않았습니다",
        )
    else:
        try:
            completed_run = run_xjtu_lstm_analysis_from_source(
                source_path,
                analysis_output_path,
            )
            set_analysis(completed_run.analysis)
            analysis_run_output = mo.callout(
                "분석이 완료되어 현재 화면을 새 결과로 갱신했습니다. "
                f"결과 파일: `{completed_run.result_path}`",
                kind="success",
                title="분석 완료",
            )
        except AnalysisRunError as error:
            analysis_run_output = mo.callout(
                f"분석을 완료하지 못했습니다. {error}",
                kind="danger",
                title="분석 실패",
            )

    run_analysis_view = mo.vstack(
        [
            mo.md("## 새 분석 실행"),
            mo.md(
                "준비된 XJTU-SY 데이터 폴더를 지정하면 데이터 확인부터 특징 추출, "
                "LSTM 분석, 결과 저장까지 기존 분석 경로를 실행합니다."
            ),
            analysis_source_input,
            mo.md(
                f"결과 저장 위치: `{analysis_output_path}`  \n"
                "실제 분석 실행에는 deep-learning 의존성이 필요합니다."
            ),
            analysis_run_button,
            analysis_run_output,
        ],
        gap=1.2,
    )
    return (run_analysis_view,)


@app.cell
def _(analysis, mo):
    def facts_table(stage):
        rows = "\n".join(
            f"| {fact.label} | {str(fact.value).replace('|', '&#124;')} |" for fact in stage.facts
        )
        if not rows:
            rows = "| - | - |"
        return mo.md("| 항목 | 값 |\n| --- | --- |\n" + rows)

    stage_by_name = {stage.name: stage for stage in analysis.inspection.stages}
    return facts_table, stage_by_name


@app.cell
def _(
    asset_selector,
    mo,
    plt,
    review_intervals,
    review_threshold,
    selected_asset,
):
    score_figure, score_axis = plt.subplots(figsize=(11, 4.5))
    score_axis.plot(
        [observation.acquisition_index for observation in selected_asset.observations],
        [observation.score for observation in selected_asset.observations],
        linewidth=1.2,
    )
    score_axis.axhline(review_threshold.value, linestyle="--", linewidth=1.0)
    for interval in review_intervals:
        score_axis.axvspan(
            interval.start_acquisition_index,
            interval.end_acquisition_index,
            alpha=0.12,
        )
    score_axis.set_xlabel("Acquisition index")
    score_axis.set_ylabel("Reconstruction mismatch score")
    score_axis.set_title(f"{selected_asset.asset_id} anomaly-score trajectory")
    score_axis.grid(alpha=0.2)
    score_figure.tight_layout()

    interval_rows = "\n".join(
        f"| {interval.start_acquisition_index} | {interval.end_acquisition_index} | "
        f"{interval.observation_count} | {interval.peak_score:.6f} |"
        for interval in sorted(
            review_intervals,
            key=lambda item: item.peak_score,
            reverse=True,
        )[:10]
    )
    if not interval_rows:
        interval_rows = "| - | - | 0 | - |"

    summary_view = mo.vstack(
        [
            mo.md("## 분석 요약"),
            asset_selector,
            mo.hstack(
                [
                    mo.stat(
                        f"{selected_asset.score_window_count:,}",
                        label="분석 구간",
                        caption="시간 순서에 맞춘 분석 window",
                    ),
                    mo.stat(
                        f"{selected_asset.acquisition_order_spearman_rho:.3f}",
                        label="시간에 따른 변화",
                        caption="Spearman rho",
                    ),
                    mo.stat(
                        f"{len(review_intervals)}",
                        label="집중 확인 구간",
                        caption="검토 기준값 초과 구간",
                    ),
                    mo.stat(
                        f"{review_threshold.value:.4f}",
                        label="검토 기준값",
                        caption="초기 구간 점수의 q95",
                    ),
                ],
                widths="equal",
            ),
            score_figure,
            mo.md(
                "### 점수가 높았던 구간\n\n"
                "| 시작 | 종료 | 구간 수 | 최고 점수 |\n"
                "| ---: | ---: | ---: | ---: |\n" + interval_rows
            ),
            mo.callout(
                "음영 구간은 이상 점수가 상대적으로 높았던 위치를 빠르게 확인하기 위한 "
                "검토용 표시입니다. 모델과 검증 세부 정보는 **상세 정보**에서 확인할 수 있습니다.",
                kind="info",
                title="그래프 읽는 방법",
            ),
        ],
        gap=1.2,
    )
    return (summary_view,)


@app.cell
def _(analysis, mo, plt, selected_asset):
    residual_pairs = sorted(
        zip(
            analysis.require_anomaly_evidence().feature_names,
            selected_asset.mean_feature_residuals,
            strict=True,
        ),
        key=lambda pair: pair[1],
    )
    residual_figure, residual_axis = plt.subplots(figsize=(11, 6))
    residual_axis.barh(
        [name.removeprefix("feature.") for name, _ in residual_pairs],
        [value for _, value in residual_pairs],
    )
    residual_axis.set_xlabel("Mean squared residual in robust-scaled feature space")
    residual_axis.set_title(f"{selected_asset.asset_id} model residual evidence")
    residual_axis.grid(axis="x", alpha=0.2)
    residual_figure.tight_layout()

    top_observations = sorted(
        selected_asset.observations,
        key=lambda observation: observation.score,
        reverse=True,
    )[:10]
    top_rows = "\n".join(
        f"| {observation.acquisition_index} | "
        f"`{observation.source_observation_id}` | {observation.score:.6f} |"
        for observation in top_observations
    )

    evidence_view = mo.vstack(
        [
            mo.md("## 이상 근거"),
            mo.md("모델이 크게 다르게 재구성한 특징과 점수가 높았던 관측값을 확인합니다."),
            residual_figure,
            mo.md(
                "### 점수가 높았던 관측값\n\n"
                "| Acquisition | 원본 관측값 | 점수 |\n"
                "| ---: | --- | ---: |\n" + top_rows
            ),
        ],
        gap=1.2,
    )
    return (evidence_view,)


@app.cell
def _(
    AnalysisExplanationError,
    explanation_api_key,
    explanation_configured,
    explanation_context,
    explanation_model,
    explanation_question,
    explanation_run,
    explanation_scope,
    generate_openai_analysis_explanation,
    generate_openai_prognostics_explanation,
    mo,
    prognostics_context_error,
    prognostics_explanation_context,
):
    _explains_prognostics = explanation_scope.value == "RUL 분석 결과"
    if _explains_prognostics:
        _boundary = (
            "저장된 RUL 분석 결과를 설명합니다. RUL 값을 다시 계산하거나 물리적 고장 시점, "
            "경보, 정비 우선순위 또는 신뢰구간을 새로 만들지 않습니다."
        )
        _context_note = (
            "설명에 사용하는 정보: 모델별 저장된 RUL 값, target 의미와 단위, "
            "검증 오차, 기능 범위, 주요 실행 정보."
        )
    else:
        _boundary = (
            "저장된 PHM 분석 결과를 설명합니다. 수치를 다시 계산하거나 고장 진단, 경보, "
            "정비 우선순위 또는 RUL을 새로 만들지 않습니다."
        )
        _context_note = (
            "설명에 사용하는 정보: 점수가 높았던 관측값, 특징 잔차, 기능 범위, 주요 실행 정보."
        )

    if not explanation_configured:
        explanation_output = mo.callout(
            "AI 설명을 사용하려면 실행 환경에 OPENAI_API_KEY와 "
            "INDUSTRIAL_PHM_GENAI_MODEL을 설정하세요.",
            kind="info",
            title="AI 설명 설정 필요",
        )
    elif _explains_prognostics and prognostics_explanation_context is None:
        explanation_output = mo.callout(
            prognostics_context_error,
            kind="warn",
            title="RUL 분석 결과 없음",
        )
    elif not explanation_run.value:
        explanation_output = mo.callout(
            "AI 설명 생성 버튼을 눌렀을 때만 모델을 호출합니다. 이 기능은 정리된 분석 정보만 "
            "전송하며 원본 센서 trajectory는 전송하지 않습니다.",
            kind="info",
            title="준비됨",
        )
    elif _explains_prognostics:
        try:
            explanation_output = mo.md(
                generate_openai_prognostics_explanation(
                    prognostics_explanation_context,
                    api_key=explanation_api_key,
                    model=explanation_model,
                    question=explanation_question.value.strip() or None,
                )
            )
        except AnalysisExplanationError as error:
            explanation_output = mo.callout(
                str(error),
                kind="danger",
                title="AI 설명 실패",
            )
    else:
        try:
            explanation_output = mo.md(
                generate_openai_analysis_explanation(
                    explanation_context,
                    api_key=explanation_api_key,
                    model=explanation_model,
                    question=explanation_question.value.strip() or None,
                )
            )
        except AnalysisExplanationError as error:
            explanation_output = mo.callout(
                str(error),
                kind="danger",
                title="AI 설명 실패",
            )

    ai_explanation_view = mo.vstack(
        [
            mo.md("## AI 설명"),
            mo.callout(_boundary, kind="warn", title="AI 설명 범위"),
            explanation_scope,
            explanation_question,
            explanation_run,
            mo.md(f"사용 모델: `{explanation_model or '설정되지 않음'}`  \n{_context_note}"),
            explanation_output,
        ],
        gap=1.2,
    )
    return (ai_explanation_view,)


@app.cell
def _(analysis, mo):
    stage_selector = mo.ui.dropdown(
        options=[stage.name for stage in analysis.inspection.stages],
        value="Scoring",
        label="분석 단계",
    )
    return (stage_selector,)


@app.cell
def _(analysis, facts_table, mo, stage_by_name, stage_selector):
    selected_stage = stage_by_name[stage_selector.value]
    warning_block = (
        mo.callout(
            mo.md("\n".join(f"- {warning}" for warning in selected_stage.warnings)),
            kind="warn",
            title="단계 경고",
        )
        if selected_stage.warnings
        else mo.callout("이 단계에 기록된 경고가 없습니다.", kind="success")
    )

    details_view = mo.vstack(
        [
            mo.md("## 상세 정보"),
            mo.callout(
                "현재 화면의 결과가 어떤 데이터와 분석 단계에서 만들어졌는지 보여주는 "
                "기술 정보입니다.",
                kind="info",
            ),
            stage_selector,
            mo.md(f"### {selected_stage.name} · {selected_stage.status}"),
            facts_table(selected_stage),
            warning_block,
            mo.md(
                f"결과 분류: **{analysis.evidence_class}**  \n"
                f"점수 의미: **{analysis.require_anomaly_evidence().score_semantics_id}**  \n"
                f"점수 방향: **{analysis.require_anomaly_evidence().score_direction}**  \n"
                f"결과 파일: `{analysis.artifact_path}`"
            ),
        ],
        gap=1.2,
    )
    return (details_view,)


@app.cell
def _(AnalysisViewError, Path, load_xjtu_rul_analysis_view, os):
    prognostics_artifact_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_PROGNOSTICS_ARTIFACT",
            "docs/research/results/xjtu-sy-rul-three-model-fold-1-validation-v1.json",
        )
    )
    if prognostics_artifact_path.is_file():
        try:
            prognostics_analysis = load_xjtu_rul_analysis_view(prognostics_artifact_path)
            prognostics_error = ""
        except AnalysisViewError as error:
            prognostics_analysis = None
            prognostics_error = str(error)
    else:
        prognostics_analysis = None
        prognostics_error = f"No prognostics evidence artifact at `{prognostics_artifact_path}`."
    return prognostics_analysis, prognostics_error


@app.cell
def _(analysis, compare_analysis_evidence, prognostics_analysis):
    prognostics_compatibility = (
        None
        if prognostics_analysis is None
        else compare_analysis_evidence(analysis, prognostics_analysis)
    )
    return (prognostics_compatibility,)


@app.cell
def _(
    analysis,
    asset_selector,
    mo,
    prognostics_analysis,
    prognostics_compatibility,
    prognostics_error,
    summarize_prognostics_for_asset,
):
    if prognostics_analysis is None:
        prognostics_view = mo.vstack(
            [
                mo.md("## RUL 분석"),
                mo.callout(
                    prognostics_error
                    + " 현재 분석에 연결할 RUL 결과가 없습니다.",
                    kind="neutral",
                    title="RUL 분석 결과 없음",
                ),
            ],
            gap=1.2,
        )
    elif prognostics_compatibility is None or not prognostics_compatibility.compatible:
        _reasons = (
            "결과 범위 호환성을 확인할 수 없습니다."
            if prognostics_compatibility is None
            else "\n".join(f"- {reason}" for reason in prognostics_compatibility.reasons)
        )
        prognostics_view = mo.vstack(
            [
                mo.md("## RUL 분석"),
                mo.callout(
                    "연결된 RUL 결과의 데이터 범위가 현재 이상 분석 결과와 맞지 않아 "
                    "같은 화면에 표시하지 않습니다.\n\n" + _reasons,
                    kind="danger",
                    title="현재 결과와 함께 표시할 수 없음",
                ),
            ],
            gap=1.2,
        )
    else:
        prognostics_summary = summarize_prognostics_for_asset(
            prognostics_analysis,
            asset_selector.value,
        )
        _low, _high = prognostics_summary.estimate_range
        _method_rows = "\n".join(
            f"| `{row.method_id}` | {row.last_recorded_remaining_useful_life:,.1f} | "
            f"{row.mean_absolute_error:,.1f} | {row.mean_signed_error:,.1f} | "
            f"{row.prediction_count:,} |"
            for row in prognostics_summary.methods
        )
        prognostics_view = mo.vstack(
            [
                mo.md("## RUL 분석"),
                asset_selector,
                mo.callout(
                    "RUL 결과는 별도의 저장된 분석 결과에서 가져옵니다. 데이터 범위는 현재 이상 "
                    "분석 결과와 맞지만 두 결과는 하나의 실행에서 만들어진 것은 아닙니다. "
                    f"이상 분석 revision: `{analysis.identity.code_revision}`. "
                    f"RUL 분석 revision: `{prognostics_analysis.identity.code_revision}`.",
                    kind="info",
                    title="별도 분석 결과",
                ),
                mo.callout(
                    "아래 값은 저장된 데이터로 평가한 **RUL 분석 결과**이며 실시간 설비 잔여수명 값이 "
                    "아닙니다. 한 단위는 "
                    f"**{prognostics_summary.target_description}**입니다.",
                    kind="warn",
                    title="RUL 값의 의미",
                ),
                mo.hstack(
                    [
                        mo.stat(
                            f"{_low:,.1f} to {_high:,.1f}",
                            label="모델별 예측 범위",
                            caption=f"{len(prognostics_summary.methods)}개 모델 비교",
                        ),
                        mo.stat(
                            "acquisition "
                            f"{prognostics_summary.methods[0].last_recorded_acquisition_index:,}",
                            label="기준 acquisition",
                            caption="마지막 기록 acquisition",
                        ),
                        mo.stat(
                            "없음",
                            label="불확실성 구간",
                            caption="보정된 구간 없음",
                        ),
                        mo.stat(
                            "미검증",
                            label="물리적 고장 기준",
                            caption="recorded endpoint 기준",
                        ),
                    ],
                    widths="equal",
                ),
                mo.md(
                    "### 모델 비교\n\n"
                    "| 모델 | 저장된 RUL 예측 | MAE | Signed error | 예측 수 |\n"
                    "| --- | ---: | ---: | ---: | ---: |\n" + _method_rows
                ),
                mo.callout(
                    "현재 이 설비의 대표 RUL 모델은 별도로 지정하지 않습니다. 아래 표는 여러 모델의 "
                    "저장된 검증 결과를 비교합니다.",
                    kind="warn",
                    title="대표 모델 미선택",
                ),
                mo.md(
                    "### 기술 정보\n\n"
                    f"- Target 정의: `{prognostics_summary.target_definition_id}`\n"
                    f"- 평가 범위: {prognostics_summary.support_definition}, acquisition "
                    f"{prognostics_summary.support_first_acquisition}부터 "
                    f"{prognostics_summary.support_prediction_count:,}개 예측\n"
                    f"- 결과 분류: {prognostics_summary.evidence_class}\n"
                    f"- 결과 파일: `{prognostics_summary.artifact_path}`"
                ),
            ]
            + (
                [
                    mo.callout(
                        "하나 이상의 모델에서 음수 RUL 예측값이 기록되었습니다. 현재 target은 0으로 "
                        "강제 보정하지 않으므로 저장된 값을 그대로 표시합니다.",
                        kind="danger",
                        title="음수 RUL 예측값 기록됨",
                    )
                ]
                if prognostics_summary.has_negative_estimate
                else []
            ),
            gap=1.2,
        )
    return (prognostics_view,)


@app.cell
def _(asset_selector, mo, os):
    report_output_input = mo.ui.text(
        value=os.environ.get(
            "INDUSTRIAL_PHM_REPORT_OUTPUT",
            f"artifacts/reports/{asset_selector.value}.md",
        ),
        label="보고서 저장 경로",
        full_width=True,
    )
    report_run_button = mo.ui.run_button(label="Markdown 보고서 저장", kind="success")
    return report_output_input, report_run_button


@app.cell
def _(
    AnalysisReportError,
    Path,
    analysis,
    asset_selector,
    mo,
    prognostics_analysis,
    prognostics_compatibility,
    report_output_input,
    report_run_button,
    write_analysis_report_markdown,
):
    if not report_run_button.value:
        report_output = mo.callout(
            "현재 선택한 설비의 분석 결과를 Markdown 파일로 저장할 수 있습니다.",
            kind="info",
            title="보고서 준비",
        )
    else:
        try:
            output_path = Path(report_output_input.value.strip())
            attached_prognostics = (
                prognostics_analysis
                if prognostics_compatibility is not None and prognostics_compatibility.compatible
                else None
            )
            write_analysis_report_markdown(
                analysis,
                asset_selector.value,
                output_path,
                prognostics=attached_prognostics,
            )
            report_output = mo.callout(
                f"보고서를 저장했습니다: `{output_path}`",
                kind="success",
                title="보고서 저장 완료",
            )
        except (OSError, AnalysisReportError) as error:
            report_output = mo.callout(
                f"보고서를 저장하지 못했습니다. {error}",
                kind="danger",
                title="보고서 저장 실패",
            )

    report_view = mo.vstack(
        [
            mo.md("## 보고서 저장"),
            report_output_input,
            report_run_button,
            report_output,
        ],
        gap=1.2,
    )
    return (report_view,)


@app.cell
def _(
    ai_explanation_view,
    details_view,
    evidence_view,
    header,
    mo,
    prognostics_view,
    report_view,
    run_analysis_view,
    summary_view,
    view_selector,
):
    views = {
        "분석 요약": summary_view,
        "이상 근거": evidence_view,
        "RUL 분석": prognostics_view,
        "AI 설명": ai_explanation_view,
        "새 분석 실행": run_analysis_view,
        "보고서 저장": report_view,
        "상세 정보": details_view,
    }
    mo.vstack([header, view_selector, views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
