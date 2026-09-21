import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt

    from industrial_phm.analysis import AnalysisViewError, load_xjtu_lstm_analysis_view
    from industrial_phm.genai import (
        AnalysisExplanationError,
        build_analysis_explanation_context,
        generate_openai_analysis_explanation,
    )

    return (
        AnalysisExplanationError,
        AnalysisViewError,
        Path,
        build_analysis_explanation_context,
        generate_openai_analysis_explanation,
        load_xjtu_lstm_analysis_view,
        mo,
        os,
        plt,
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
        analysis = load_xjtu_lstm_analysis_view(artifact_path)
    except AnalysisViewError as error:
        mo.stop(
            True,
            mo.callout(str(error), kind="danger", title="Analysis validation failed"),
        )

    return analysis, artifact_path


@app.cell
def _(analysis, mo):
    asset_selector = mo.ui.dropdown(
        options=[asset.asset_id for asset in analysis.assets],
        value=analysis.assets[0].asset_id,
        label="Analysis target",
    )
    view_selector = mo.ui.radio(
        options=["Analysis Summary", "Evidence", "AI Explanation", "Analysis Details"],
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
def _(analysis, asset_selector):
    selected_asset = analysis.asset(asset_selector.value)
    return (selected_asset,)


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
def _(analysis, asset_selector, mo, plt, selected_asset):
    score_figure, score_axis = plt.subplots(figsize=(11, 4.5))
    score_axis.plot(
        [observation.acquisition_index for observation in selected_asset.observations],
        [observation.score for observation in selected_asset.observations],
        linewidth=1.2,
    )
    score_axis.set_xlabel("Acquisition index")
    score_axis.set_ylabel("Reconstruction mismatch score")
    score_axis.set_title(f"{selected_asset.asset_id} anomaly-evidence trajectory")
    score_axis.grid(alpha=0.2)
    score_figure.tight_layout()

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
                        f"{selected_asset.late_vs_middle_rank_probability:.3f}",
                        label="Late vs middle",
                        caption="retrospective evidence",
                    ),
                    mo.stat(
                        "Unavailable",
                        label="Anomaly intervals",
                        caption="validated threshold not recorded",
                    ),
                ],
                widths="equal",
            ),
            score_figure,
            mo.callout(
                "Higher score means larger reconstruction mismatch in this analysis. "
                "No validated threshold is recorded, so this view does not create a "
                "normal/fault state or anomaly interval yet.",
                kind="warn",
                title="Current interpretation boundary",
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
    summary_view,
    view_selector,
):
    views = {
        "Analysis Summary": summary_view,
        "Evidence": evidence_view,
        "AI Explanation": ai_explanation_view,
        "Analysis Details": details_view,
    }
    mo.vstack([header, view_selector, views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
