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
        AnalysisRunError,
        AnalysisViewError,
        derive_early_scored_window_review_threshold,
        load_xjtu_lstm_analysis_view,
        run_xjtu_lstm_analysis_from_source,
        score_exceedance_intervals,
    )
    from industrial_phm.genai import (
        AnalysisExplanationError,
        build_analysis_explanation_context,
        generate_openai_analysis_explanation,
    )

    return (
        AnalysisExplanationError,
        AnalysisRunError,
        AnalysisViewError,
        Path,
        build_analysis_explanation_context,
        derive_early_scored_window_review_threshold,
        generate_openai_analysis_explanation,
        load_xjtu_lstm_analysis_view,
        mo,
        os,
        plt,
        run_xjtu_lstm_analysis_from_source,
        score_exceedance_intervals,
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
            f"Analysis artifact was not found: `{artifact_path}`",
            kind="warn",
            title="Analysis unavailable",
        ),
    )

    try:
        initial_analysis = load_xjtu_lstm_analysis_view(artifact_path)
    except AnalysisViewError as error:
        mo.stop(
            True,
            mo.callout(str(error), kind="danger", title="Analysis validation failed"),
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
        options=[asset.asset_id for asset in analysis.assets],
        value=analysis.assets[0].asset_id,
        label="Analysis target",
    )
    view_selector = mo.ui.radio(
        options=[
            "Analysis Summary",
            "Evidence",
            "AI Explanation",
            "Run Analysis",
            "Analysis Details",
        ],
        value="Analysis Summary",
        inline=True,
        label="View",
    )
    header = mo.md(
        """
        # PHM Analysis Explorer

        Review recorded PHM analysis evidence from a validated result without reading
        experiment JSON directly. User-facing results come first; pipeline and provenance
        remain available as drill-down details.
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
    selected_asset = analysis.asset(asset_selector.value)
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
        label="Ask about this analysis",
        rows=3,
        full_width=True,
    )
    explanation_run = mo.ui.run_button(
        label="Generate AI explanation",
        kind="success",
    )
    return explanation_question, explanation_run


@app.cell
def _(mo, os):
    analysis_source_input = mo.ui.text(
        value=os.environ.get("INDUSTRIAL_PHM_XJTU_SOURCE", ""),
        label="Prepared XJTU-SY source",
        full_width=True,
    )
    analysis_output_input = mo.ui.text(
        value=os.environ.get(
            "INDUSTRIAL_PHM_ANALYSIS_OUTPUT",
            "artifacts/analysis/xjtu-lstm-analysis.json",
        ),
        label="Result artifact path",
        full_width=True,
    )
    analysis_revision_input = mo.ui.text(
        value=os.environ.get("INDUSTRIAL_PHM_CODE_REVISION", ""),
        label="Code revision (40-character Git SHA)",
        full_width=True,
    )
    analysis_run_button = mo.ui.run_button(
        label="Run XJTU LSTM analysis",
        kind="success",
    )
    return (
        analysis_output_input,
        analysis_revision_input,
        analysis_run_button,
        analysis_source_input,
    )


@app.cell
def _(
    AnalysisRunError,
    Path,
    analysis_output_input,
    analysis_revision_input,
    analysis_run_button,
    analysis_source_input,
    mo,
    run_xjtu_lstm_analysis_from_source,
    set_analysis,
):
    if not analysis_run_button.value:
        analysis_run_output = mo.callout(
            "Configure a prepared XJTU-SY source, result path, and exact code revision, "
            "then run the existing frozen LSTM analysis path. The current loaded result "
            "remains active until a new execution completes successfully.",
            kind="info",
            title="Ready to run",
        )
    else:
        source_value = analysis_source_input.value.strip()
        output_value = analysis_output_input.value.strip()
        revision_value = analysis_revision_input.value.strip()
        missing = [
            label
            for label, value in (
                ("prepared source", source_value),
                ("result path", output_value),
                ("code revision", revision_value),
            )
            if not value
        ]
        if missing:
            analysis_run_output = mo.callout(
                "Missing required input: " + ", ".join(missing),
                kind="warn",
                title="Analysis not started",
            )
        else:
            try:
                completed_run = run_xjtu_lstm_analysis_from_source(
                    Path(source_value),
                    Path(output_value),
                    code_revision=revision_value,
                )
                set_analysis(completed_run.analysis)
                analysis_run_output = mo.callout(
                    "Analysis completed and the active Analysis Explorer result was updated. "
                    f"Artifact: `{completed_run.result_path}`",
                    kind="success",
                    title="Analysis completed",
                )
            except AnalysisRunError as error:
                analysis_run_output = mo.callout(
                    str(error),
                    kind="danger",
                    title="Analysis failed",
                )

    run_analysis_view = mo.vstack(
        [
            mo.md("## Run Analysis"),
            mo.callout(
                "This executes the existing frozen XJTU LSTM retrospective development "
                "pipeline. It validates the prepared source, extracts features, fits the "
                "model, scores the validation bearings, writes the evidence artifact, "
                "and reloads it through the same AnalysisView used by this application.",
                kind="info",
                title="Source → Python PHM analysis → user result",
            ),
            analysis_source_input,
            analysis_output_input,
            analysis_revision_input,
            analysis_run_button,
            mo.md(
                "Runtime requirement: "
                "`uv sync --locked --group research --extra deep-learning`.  \n"
                "This execution preserves retrospective-development semantics; it is not "
                "live asset inference."
            ),
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
        return mo.md("| Field | Value |\n| --- | --- |\n" + rows)

    stage_by_name = {stage.name: stage for stage in analysis.inspection.stages}
    return facts_table, stage_by_name


@app.cell
def _(
    analysis,
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
    score_axis.set_title(f"{selected_asset.asset_id} anomaly-evidence trajectory")
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
            mo.md("## Analysis Summary"),
            asset_selector,
            mo.hstack(
                [
                    mo.stat(
                        f"{selected_asset.score_window_count:,}",
                        label="Analyzed windows",
                        caption="acquisition-aligned",
                    ),
                    mo.stat(
                        f"{selected_asset.acquisition_order_spearman_rho:.3f}",
                        label="Trend association",
                        caption="Spearman rho",
                    ),
                    mo.stat(
                        f"{len(review_intervals)}",
                        label="Review intervals",
                        caption="score exceeds review threshold",
                    ),
                    mo.stat(
                        f"{review_threshold.value:.4f}",
                        label="Review threshold",
                        caption="early scored-window q95",
                    ),
                ],
                widths="equal",
            ),
            score_figure,
            mo.callout(
                "Shaded regions are score-exceedance intervals for retrospective review. "
                "The threshold is the 95th percentile of the earliest third of recorded "
                "scored windows. It is not a validated normal/fault state threshold and "
                "does not create an alarm, fault interval, or diagnosis.",
                kind="warn",
                title="Review-threshold semantics",
            ),
            mo.md(
                "### Highest score-exceedance intervals\n\n"
                "| Start | End | Windows | Peak score |\n"
                "| ---: | ---: | ---: | ---: |\n" + interval_rows
            ),
            mo.md(
                "### Available now\n\n"
                + "\n".join(f"- {item}" for item in analysis.available_capabilities)
            ),
            mo.md(
                "### Not available in this result\n\n"
                + "\n".join(f"- {item}" for item in analysis.unsupported_capabilities)
            ),
        ],
        gap=1.2,
    )
    return (summary_view,)


@app.cell
def _(analysis, mo, plt, selected_asset):
    residual_pairs = sorted(
        zip(analysis.feature_names, selected_asset.mean_feature_residuals, strict=True),
        key=lambda pair: pair[1],
    )
    residual_figure, residual_axis = plt.subplots(figsize=(11, 6))
    residual_axis.barh(
        [name.removeprefix("feature.") for name, _ in residual_pairs],
        [value for _, value in residual_pairs],
    )
    residual_axis.set_xlabel("Mean squared residual in robust-scaled feature space")
    residual_axis.set_title(f"{selected_asset.asset_id} supporting model evidence")
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
            mo.md("## Evidence"),
            residual_figure,
            mo.callout(
                "Feature residuals are reconstruction mismatch evidence in model space. "
                "They are not a physical fault contribution or root-cause diagnosis.",
                kind="info",
                title="Evidence semantics",
            ),
            mo.md(
                "### Highest recorded scores\n\n"
                "| Acquisition | Source observation | Score |\n"
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
    generate_openai_analysis_explanation,
    mo,
):
    if not explanation_configured:
        explanation_output = mo.callout(
            "Set OPENAI_API_KEY and INDUSTRIAL_PHM_GENAI_MODEL in the application "
            "environment to enable generative explanation.",
            kind="info",
            title="AI explanation is not configured",
        )
    elif not explanation_run.value:
        explanation_output = mo.callout(
            "The model is called only when you press Generate AI explanation. "
            "Only bounded structured analysis evidence is sent; the raw sensor trajectory "
            "is not sent by this feature.",
            kind="info",
            title="Ready",
        )
    else:
        try:
            generated_explanation = generate_openai_analysis_explanation(
                explanation_context,
                api_key=explanation_api_key,
                model=explanation_model,
                question=explanation_question.value.strip() or None,
            )
            explanation_output = mo.md(generated_explanation)
        except AnalysisExplanationError as error:
            explanation_output = mo.callout(
                str(error),
                kind="danger",
                title="AI explanation failed",
            )

    ai_explanation_view = mo.vstack(
        [
            mo.md("## AI Explanation"),
            mo.callout(
                "This layer explains recorded PHM evidence; it does not replace the "
                "numerical analysis or create unsupported diagnosis, alarm/state, "
                "maintenance priority, health indicator, or RUL.",
                kind="warn",
                title="Generative AI boundary",
            ),
            explanation_question,
            explanation_run,
            mo.md(
                f"Model: `{explanation_model or 'not configured'}`  \n"
                "Context: top recorded scores, feature residual evidence, capability "
                "limits, and selected pipeline/provenance facts."
            ),
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
        label="Pipeline stage",
    )
    return (stage_selector,)


@app.cell
def _(analysis, facts_table, mo, stage_by_name, stage_selector):
    selected_stage = stage_by_name[stage_selector.value]
    warning_block = (
        mo.callout(
            mo.md("\n".join(f"- {warning}" for warning in selected_stage.warnings)),
            kind="warn",
            title="Stage warnings",
        )
        if selected_stage.warnings
        else mo.callout("No warnings recorded for this stage.", kind="success")
    )

    details_view = mo.vstack(
        [
            mo.md("## Analysis Details"),
            mo.callout(
                "These details explain how the displayed evidence was produced. "
                "They are drill-down transparency, not the primary user result.",
                kind="info",
            ),
            stage_selector,
            mo.md(f"### {selected_stage.name} · {selected_stage.status}"),
            facts_table(selected_stage),
            warning_block,
            mo.md(
                f"Evidence class: **{analysis.evidence_class}**  \n"
                f"Score semantics: **{analysis.score_semantics_id}**  \n"
                f"Direction: **{analysis.score_direction}**  \n"
                f"Artifact: `{analysis.artifact_path}`"
            ),
        ],
        gap=1.2,
    )
    return (details_view,)


@app.cell
def _(
    ai_explanation_view,
    details_view,
    evidence_view,
    header,
    mo,
    run_analysis_view,
    summary_view,
    view_selector,
):
    views = {
        "Analysis Summary": summary_view,
        "Evidence": evidence_view,
        "AI Explanation": ai_explanation_view,
        "Run Analysis": run_analysis_view,
        "Analysis Details": details_view,
    }
    mo.vstack([header, view_selector, views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
