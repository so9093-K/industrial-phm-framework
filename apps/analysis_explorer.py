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
        AnalysisViewError,
        derive_early_scored_window_review_threshold,
        load_xjtu_lstm_analysis_view,
        score_exceedance_intervals,
    )

    return (
        AnalysisViewError,
        Path,
        derive_early_scored_window_review_threshold,
        load_xjtu_lstm_analysis_view,
        mo,
        os,
        plt,
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
        options=["Analysis Summary", "Evidence", "Analysis Details"],
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
                "does not create an alarm or diagnosis.",
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
def _(details_view, evidence_view, header, mo, summary_view, view_selector):
    views = {
        "Analysis Summary": summary_view,
        "Evidence": evidence_view,
        "Analysis Details": details_view,
    }
    mo.vstack([header, view_selector, views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
