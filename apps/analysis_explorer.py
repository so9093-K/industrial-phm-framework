import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from datetime import UTC, datetime
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt

    from industrial_phm.analysis import (
        AnalysisReportError,
        AnalysisReviewRecord,
        AnalysisRunError,
        AnalysisViewError,
        JsonAnalysisReviewRepository,
        analysis_artifact_sha256,
        compare_analysis_evidence,
        plan_xjtu_lstm_analysis,
        run_xjtu_lstm_analysis_from_source,
        summarize_anomaly_for_asset,
        summarize_prognostics_for_asset,
        write_analysis_report_markdown,
    )
    from industrial_phm.analysis.loader import load_analysis_surface, load_analysis_view
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
        AnalysisReviewRecord,
        JsonAnalysisReviewRepository,
        Path,
        analysis_artifact_sha256,
        build_analysis_explanation_context,
        build_prognostics_explanation_context,
        compare_analysis_evidence,
        datetime,
        generate_openai_analysis_explanation,
        generate_openai_prognostics_explanation,
        load_analysis_surface,
        load_analysis_view,
        mo,
        os,
        plan_xjtu_lstm_analysis,
        plt,
        run_xjtu_lstm_analysis_from_source,
        summarize_anomaly_for_asset,
        summarize_prognostics_for_asset,
        UTC,
        write_analysis_report_markdown,
    )


@app.cell
def _(AnalysisViewError, Path, load_analysis_surface, mo, os):
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
        initial_surface = load_analysis_surface(artifact_path)
    except AnalysisViewError as error:
        mo.stop(
            True,
            mo.callout(str(error), kind="danger", title="분석 결과 검증 실패"),
        )

    if initial_surface.analysis is None:
        _stage_views = []
        for _stage in initial_surface.inspection.stages:
            _fact_rows = "\n".join(
                f"| {_fact.label} | {str(_fact.value).replace('|', '&#124;')} |"
                for _fact in _stage.facts
            )
            if not _fact_rows:
                _fact_rows = "| - | - |"
            _stage_items = [
                mo.md(
                    f"### {_stage.name}\n\n"
                    f"Status: **{_stage.status}**\n\n"
                    "| 항목 | 값 |\n"
                    "| --- | --- |\n" + _fact_rows
                )
            ]
            if _stage.warnings:
                _stage_items.append(
                    mo.callout(
                        mo.md("\n".join(f"- {_warning}" for _warning in _stage.warnings)),
                        kind="warn",
                        title=f"{_stage.name} 경고",
                    )
                )
            _stage_views.append(mo.vstack(_stage_items, gap=0.8))

        _inspection_only_view = mo.vstack(
            [
                mo.md(
                    "# PHM 분석 Explorer\n\n"
                    "이 artifact는 검증된 pipeline/capability 정보까지 확인할 수 있습니다."
                ),
                mo.callout(
                    "현재 schema에는 Explorer가 표시할 observation-level anomaly trajectory 또는 "
                    "RUL detailed projector가 없습니다. 저장된 inspection evidence만 표시하며, "
                    "artifact에 없는 점수 trajectory나 진단 결과를 새로 만들지 않습니다.",
                    kind="info",
                    title="Inspection-only 결과",
                ),
                mo.md(
                    "### Artifact\n\n"
                    f"- Schema: `{initial_surface.inspection.schema_id}`\n"
                    f"- Status: **{initial_surface.inspection.status}**\n"
                    f"- File: `{initial_surface.artifact_path}`"
                ),
                *_stage_views,
            ],
            gap=1.2,
        )
        mo.stop(True, _inspection_only_view)

    initial_analysis = initial_surface.analysis
    assert initial_analysis is not None
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
def _(JsonAnalysisReviewRepository, Path, os):
    review_state_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_ANALYSIS_REVIEW_STATE",
            "artifacts/analysis/review-state.json",
        )
    )
    review_repository = JsonAnalysisReviewRepository(review_state_path)
    return review_repository, review_state_path


@app.cell
def _(Path, analysis, analysis_artifact_sha256):
    try:
        review_artifact_sha256 = analysis_artifact_sha256(Path(analysis.artifact_path))
        review_artifact_error = ""
    except (OSError, ValueError) as error:
        review_artifact_sha256 = None
        review_artifact_error = str(error)
    return review_artifact_error, review_artifact_sha256


@app.cell
def _(analysis, mo):
    asset_selector = mo.ui.dropdown(
        options=[asset.asset_id for asset in analysis.require_anomaly_evidence().assets],
        value=analysis.require_anomaly_evidence().assets[0].asset_id,
        label="분석 대상",
    )
    view_selector = mo.ui.radio(
        options=[
            "결과 요약",
            "검토 및 조치",
            "근거 확인",
            "RUL 분석",
            "새 분석 실행",
            "보고서 저장",
            "상세 정보",
        ],
        value="결과 요약",
        inline=True,
        label="보기",
    )
    header = mo.md(
        """
        # PHM 분석 Explorer

        저장된 분석 결과에서 **어디를 먼저 확인해야 하는지**부터 보여줍니다.
        근거와 모델·실행 정보는 필요할 때 단계적으로 확인할 수 있습니다.
        """
    )
    return asset_selector, header, view_selector


@app.cell
def _(analysis, asset_selector, summarize_anomaly_for_asset):
    anomaly_summary = summarize_anomaly_for_asset(analysis, asset_selector.value)
    selected_asset = anomaly_summary.asset
    review_threshold = anomaly_summary.review_threshold
    review_intervals = anomaly_summary.review_intervals
    return anomaly_summary, review_intervals, review_threshold, selected_asset


@app.cell
def _(mo):
    review_note_input = mo.ui.text_area(
        value="",
        label="검토 메모 (선택)",
        rows=3,
        full_width=True,
    )
    review_acknowledge_button = mo.ui.run_button(
        label="검토 완료로 표시",
        kind="success",
    )
    return review_acknowledge_button, review_note_input


@app.cell
def _(
    AnalysisReviewRecord,
    analysis,
    anomaly_summary,
    asset_selector,
    datetime,
    review_acknowledge_button,
    review_artifact_error,
    review_artifact_sha256,
    review_note_input,
    review_repository,
    UTC,
):
    review_record = None
    review_record_error = review_artifact_error
    if review_artifact_sha256 is not None:
        try:
            if review_acknowledge_button.value and anomaly_summary.review_interval_count > 0:
                review_repository.record(
                    AnalysisReviewRecord(
                        artifact_path=analysis.artifact_path,
                        artifact_sha256=review_artifact_sha256,
                        asset_id=asset_selector.value,
                        review_policy_id=anomaly_summary.review_threshold.policy_id,
                        review_threshold_value=anomaly_summary.review_threshold.value,
                        review_interval_count=anomaly_summary.review_interval_count,
                        reviewed_at=datetime.now(UTC),
                        note=review_note_input.value.strip(),
                    )
                )
            review_record = review_repository.get(
                artifact_sha256=review_artifact_sha256,
                asset_id=asset_selector.value,
                review_policy_id=anomaly_summary.review_threshold.policy_id,
            )
        except (OSError, ValueError) as error:
            review_record_error = str(error)
    return review_record, review_record_error


@app.cell
def _(
    anomaly_summary,
    asset_selector,
    mo,
    review_acknowledge_button,
    review_note_input,
    review_record,
    review_record_error,
    review_state_path,
):
    _strongest = anomaly_summary.strongest_review_interval

    if anomaly_summary.review_interval_count == 0:
        _status = mo.callout(
            "현재 descriptive review policy를 넘은 연속 구간이 없습니다. "
            "이 상태는 설비가 정상이라는 판정이 아닙니다.",
            kind="neutral",
            title="검토 항목 없음",
        )
        _action_items = []
    elif review_record_error:
        _status = mo.callout(
            review_record_error,
            kind="danger",
            title="검토 기록을 사용할 수 없습니다",
        )
        _action_items = []
    elif review_record is not None:
        _status = mo.callout(
            f"이 분석 결과의 검토 필요 항목은 "
            f"{review_record.reviewed_at.isoformat()}에 확인 완료로 기록됐습니다.",
            kind="success",
            title="검토 완료",
        )
        _action_items = [
            mo.md(
                "### 기록된 메모\n\n"
                + (review_record.note if review_record.note else "_메모 없음_")
            )
        ]
    else:
        _status = mo.callout(
            f"검토 기준을 넘은 연속 구간이 "
            f"{anomaly_summary.review_interval_count}개 있습니다. "
            "결과 근거를 확인한 뒤 검토 완료 여부를 기록할 수 있습니다.",
            kind="warn",
            title="검토 필요",
        )
        _action_items = [
            review_note_input,
            review_acknowledge_button,
        ]

    if _strongest is None:
        _strongest_view = mo.md("### 우선 확인 구간\n\n현재 기록된 review interval이 없습니다.")
    else:
        _strongest_view = mo.md(
            "### 우선 확인 구간\n\n"
            f"- Acquisition: **{_strongest.start_acquisition_index}-"
            f"{_strongest.end_acquisition_index}**\n"
            f"- Observation 수: **{_strongest.observation_count:,}**\n"
            f"- Peak score: **{_strongest.peak_score:.6f}**\n"
            f"- Review threshold: **{anomaly_summary.review_threshold.value:.6f}**"
        )

    review_view = mo.vstack(
        [
            mo.md("## 검토 및 조치"),
            asset_selector,
            _status,
            _strongest_view,
            *_action_items,
            mo.callout(
                "이 화면의 '검토 완료'는 사람의 review disposition을 로컬 상태에 기록합니다. "
                f"기본 저장 위치는 `{review_state_path}`입니다. 이 기록은 OperationalFinding, "
                "fault diagnosis, maintenance work order 또는 CMMS 기록이 아닙니다.",
                kind="info",
                title="현재 조치 범위",
            ),
        ],
        gap=1.2,
    )
    return (review_view,)


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
            f"현재 이상 분석 결과와 연결된 RUL 분석 결과의 범위가 맞지 않습니다: {_reasons}"
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
def _(mo, os):
    analysis_source_input = mo.ui.text(
        value=os.environ.get("INDUSTRIAL_PHM_XJTU_SOURCE", ""),
        label="1. 준비된 XJTU-SY 데이터 폴더",
        full_width=True,
    )
    analysis_output_input = mo.ui.text(
        value=os.environ.get(
            "INDUSTRIAL_PHM_ANALYSIS_OUTPUT",
            "artifacts/analysis/xjtu-lstm-analysis.json",
        ),
        label="결과 저장 위치",
        full_width=True,
    )
    analysis_plan_button = mo.ui.run_button(label="2. 데이터 확인 및 실행 계획 만들기")
    analysis_run_button = mo.ui.run_button(label="3. 분석 실행", kind="success")
    return (
        analysis_output_input,
        analysis_plan_button,
        analysis_run_button,
        analysis_source_input,
    )


@app.cell
def _(mo):
    get_analysis_run_plan, set_analysis_run_plan = mo.state(None)
    return get_analysis_run_plan, set_analysis_run_plan


@app.cell
def _(Path, analysis_output_input, analysis_source_input):
    _run_source_value = analysis_source_input.value.strip()
    _run_output_value = analysis_output_input.value.strip()
    analysis_source_path = Path(_run_source_value) if _run_source_value else None
    analysis_result_path = Path(_run_output_value) if _run_output_value else Path(".")
    return analysis_result_path, analysis_source_path


@app.cell
def _(
    analysis_plan_button,
    analysis_result_path,
    analysis_source_path,
    plan_xjtu_lstm_analysis,
    set_analysis_run_plan,
):
    if analysis_plan_button.value:
        _prepared_plan = (
            None
            if analysis_source_path is None
            else plan_xjtu_lstm_analysis(analysis_source_path, analysis_result_path)
        )
        set_analysis_run_plan(_prepared_plan)
    return


@app.cell
def _(
    analysis_result_path,
    analysis_source_path,
    get_analysis_run_plan,
    mo,
):
    analysis_run_plan = get_analysis_run_plan()
    analysis_plan_is_current = (
        analysis_run_plan is not None
        and analysis_source_path == analysis_run_plan.source
        and analysis_result_path == analysis_run_plan.result_path
    )

    if analysis_source_path is None:
        analysis_plan_view = mo.callout(
            "먼저 분석할 XJTU-SY 데이터 폴더를 입력하세요.",
            kind="info",
            title="1. 데이터 선택",
        )
    elif analysis_run_plan is None:
        analysis_plan_view = mo.callout(
            "데이터 폴더와 결과 위치를 확인한 뒤 **데이터 확인 및 실행 계획 만들기**를 누르세요.",
            kind="info",
            title="2. 실행 전 확인 필요",
        )
    elif not analysis_plan_is_current:
        analysis_plan_view = mo.callout(
            "데이터 폴더 또는 결과 위치가 계획을 만든 뒤 변경되었습니다. "
            "현재 입력으로 실행 계획을 다시 확인하세요.",
            kind="warn",
            title="실행 계획이 오래되었습니다",
        )
    else:
        _plan_stage_rows = "\n".join(
            f"{index}. {stage}"
            for index, stage in enumerate(analysis_run_plan.pipeline_stages, start=1)
        )
        _plan_population = (
            "확인 불가"
            if analysis_run_plan.source_acquisition_count is None
            else (
                f"{analysis_run_plan.source_acquisition_count:,} acquisitions / "
                f"{analysis_run_plan.bearing_run_count:,} bearing runs / "
                f"{analysis_run_plan.checked_acquisition_count:,} representative checks"
            )
        )
        _plan_warnings = "\n".join(f"- {warning}" for warning in analysis_run_plan.warnings)
        _plan_blockers = "\n".join(f"- {blocker}" for blocker in analysis_run_plan.blockers)
        _plan_status = (
            mo.callout(
                "사전 검증에서 실행 차단 조건이 발견되지 않았습니다. "
                "아래 계획을 확인한 뒤 실제 분석을 실행할 수 있습니다.",
                kind="success",
                title="실행 준비됨",
            )
            if analysis_run_plan.ready_to_run
            else mo.callout(
                mo.md(_plan_blockers),
                kind="danger",
                title="실행 전 해결할 항목",
            )
        )
        analysis_plan_view = mo.vstack(
            [
                _plan_status,
                mo.md(
                    "### 확인된 데이터\n\n"
                    f"- Source: `{analysis_run_plan.source}`\n"
                    f"- Population: {_plan_population}\n"
                    f"- Result: `{analysis_run_plan.result_path}`"
                ),
                mo.md("### 실행 계획\n\n" + _plan_stage_rows),
                mo.callout(
                    mo.md(_plan_warnings),
                    kind="warn",
                    title="실행 전에 알아둘 점",
                ),
            ],
            gap=1.0,
        )
    return analysis_plan_is_current, analysis_plan_view, analysis_run_plan


@app.cell
def _(
    AnalysisRunError,
    analysis_plan_is_current,
    analysis_result_path,
    analysis_run_button,
    analysis_run_plan,
    analysis_source_path,
    mo,
    run_xjtu_lstm_analysis_from_source,
    set_analysis,
):
    if not analysis_run_button.value:
        analysis_run_output = mo.callout(
            "실제 모델 실행은 **분석 실행**을 눌렀을 때만 시작합니다.",
            kind="neutral",
            title="3. 실행 대기",
        )
    elif analysis_source_path is None:
        analysis_run_output = mo.callout(
            "분석할 데이터 폴더를 입력하고 실행 계획부터 확인하세요.",
            kind="warn",
            title="분석을 시작하지 않았습니다",
        )
    elif analysis_run_plan is None or not analysis_plan_is_current:
        analysis_run_output = mo.callout(
            "현재 입력에 대한 실행 계획을 먼저 확인하세요.",
            kind="warn",
            title="분석을 시작하지 않았습니다",
        )
    elif not analysis_run_plan.ready_to_run:
        analysis_run_output = mo.callout(
            "사전 검증의 실행 차단 항목을 해결한 뒤 계획을 다시 확인하세요.",
            kind="danger",
            title="분석을 시작하지 않았습니다",
        )
    else:
        try:
            completed_run = run_xjtu_lstm_analysis_from_source(
                analysis_source_path,
                analysis_result_path,
            )
            set_analysis(completed_run.analysis)
            analysis_run_output = mo.callout(
                "분석이 완료되어 현재 Explorer를 새 결과로 갱신했습니다. "
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
    return (analysis_run_output,)


@app.cell
def _(
    analysis_output_input,
    analysis_plan_button,
    analysis_plan_view,
    analysis_run_button,
    analysis_run_output,
    analysis_source_input,
    mo,
):
    run_analysis_view = mo.vstack(
        [
            mo.md("## 새 분석 실행"),
            mo.md(
                "실제 모델을 실행하기 전에 데이터 profile과 실행 범위를 먼저 확인합니다. "
                "계획 확인 단계에서는 numerical model fit이나 scoring을 시작하지 않습니다."
            ),
            analysis_source_input,
            analysis_output_input,
            analysis_plan_button,
            analysis_plan_view,
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
    anomaly_summary,
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

    strongest_interval = anomaly_summary.strongest_review_interval
    if strongest_interval is None:
        summary_status = mo.callout(
            "현재 결과에서는 검토 기준값을 넘은 연속 구간이 기록되지 않았습니다. "
            "이 결과만으로 정상 상태를 확정하는 것은 아닙니다.",
            kind="neutral",
            title="집중 확인 구간 없음",
        )
        strongest_interval_label = "없음"
        strongest_peak_label = "-"
    else:
        summary_status = mo.callout(
            f"검토 기준값을 넘은 구간이 {anomaly_summary.review_interval_count}개 기록되었습니다. "
            "가장 높은 점수 구간은 acquisition "
            f"{strongest_interval.start_acquisition_index}-"
            f"{strongest_interval.end_acquisition_index}입니다.",
            kind="warn",
            title="먼저 확인할 구간",
        )
        strongest_interval_label = (
            f"{strongest_interval.start_acquisition_index}-"
            f"{strongest_interval.end_acquisition_index}"
        )
        strongest_peak_label = f"{strongest_interval.peak_score:.4f}"

    summary_view = mo.vstack(
        [
            mo.md("## 결과 요약"),
            asset_selector,
            summary_status,
            mo.hstack(
                [
                    mo.stat(
                        f"{selected_asset.score_window_count:,}",
                        label="분석 구간",
                        caption="시간 순서에 맞춘 분석 window",
                    ),
                    mo.stat(
                        f"{anomaly_summary.review_interval_count}",
                        label="집중 확인 구간",
                        caption="검토 기준값 초과 연속 구간",
                    ),
                    mo.stat(
                        strongest_interval_label,
                        label="가장 높은 구간",
                        caption=f"최고 점수 {strongest_peak_label}",
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
                "음영 구간은 모델 mismatch 점수가 초기 reference보다 상대적으로 높았던 위치를 "
                "검토하기 위한 표시입니다. 고장 판정·경보·정비 우선순위를 의미하지 않습니다. "
                "수치 기준과 모델 정보는 **상세 정보**에서 확인할 수 있습니다.",
                kind="info",
                title="이 결과의 의미",
            ),
        ],
        gap=1.2,
    )
    return (summary_view,)


@app.cell
def _(anomaly_summary, mo, plt):
    residual_pairs = tuple(reversed(anomaly_summary.ranked_feature_residuals))
    _selected_asset = anomaly_summary.asset
    residual_figure, residual_axis = plt.subplots(figsize=(11, 6))
    residual_axis.barh(
        [item.feature_name.removeprefix("feature.") for item in residual_pairs],
        [item.mean_squared_residual for item in residual_pairs],
    )
    residual_axis.set_xlabel("Mean squared residual in robust-scaled feature space")
    residual_axis.set_title(f"{_selected_asset.asset_id} model residual evidence")
    residual_axis.grid(axis="x", alpha=0.2)
    residual_figure.tight_layout()

    top_rows = "\n".join(
        f"| {observation.acquisition_index} | "
        f"`{observation.source_observation_id}` | {observation.score:.6f} |"
        for observation in anomaly_summary.ranked_observations
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
def _(
    analysis,
    facts_table,
    mo,
    review_threshold,
    selected_asset,
    stage_by_name,
    stage_selector,
):
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
                f"시간 순서 상관계수(Spearman rho): "
                f"**{selected_asset.acquisition_order_spearman_rho:.3f}**  \n"
                f"검토 기준값: **{review_threshold.value:.4f}** "
                f"(`{review_threshold.policy_id}`)  \n"
                f"결과 파일: `{analysis.artifact_path}`"
            ),
        ],
        gap=1.2,
    )
    return (details_view,)


@app.cell
def _(AnalysisViewError, Path, load_analysis_view, os):
    prognostics_artifact_path = Path(
        os.environ.get(
            "INDUSTRIAL_PHM_PROGNOSTICS_ARTIFACT",
            "docs/research/results/xjtu-sy-rul-three-model-fold-1-validation-v1.json",
        )
    )
    if prognostics_artifact_path.is_file():
        try:
            prognostics_analysis = load_analysis_view(prognostics_artifact_path)
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
                    prognostics_error + " 현재 분석에 연결할 RUL 결과가 없습니다.",
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
                    "아래 값은 저장된 데이터로 평가한 **RUL 분석 결과**이며 "
                    "실시간 설비 잔여수명 값이 아닙니다. 한 단위는 "
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
                    "현재 이 설비의 대표 RUL 모델은 별도로 지정하지 않습니다. "
                    "아래 표는 여러 모델의 저장된 검증 결과를 비교합니다.",
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
                        "하나 이상의 모델에서 음수 RUL 예측값이 기록되었습니다. "
                        "현재 target은 0으로 강제 보정하지 않으므로 저장된 값을 그대로 표시합니다.",
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
    review_view,
    run_analysis_view,
    summary_view,
    view_selector,
):
    views = {
        "결과 요약": summary_view,
        "검토 및 조치": review_view,
        "근거 확인": mo.vstack([evidence_view, ai_explanation_view], gap=2.0),
        "RUL 분석": mo.vstack([prognostics_view, ai_explanation_view], gap=2.0),
        "새 분석 실행": run_analysis_view,
        "보고서 저장": report_view,
        "상세 정보": details_view,
    }
    mo.vstack([header, view_selector, views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
