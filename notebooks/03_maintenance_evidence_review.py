import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt

    from industrial_phm.experiments.result_inspection import (
        ExperimentResultInspectionError,
        inspect_experiment_result,
    )
    from industrial_phm.experiments.xjtu_lstm_result import (
        XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
    )

    return (
        ExperimentResultInspectionError,
        Path,
        XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
        inspect_experiment_result,
        json,
        mo,
        plt,
    )


@app.cell
def _(
    ExperimentResultInspectionError,
    Path,
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
    inspect_experiment_result,
    json,
    mo,
):
    artifact_path = Path(
        "docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
    )
    mo.stop(
        not artifact_path.is_file(),
        mo.callout(
            f"Version-controlled evidence artifact was not found: `{artifact_path}`",
            kind="warn",
            title="Evidence unavailable",
        ),
    )

    try:
        inspection = inspect_experiment_result(artifact_path)
    except ExperimentResultInspectionError as error:
        mo.stop(
            True,
            mo.callout(str(error), kind="danger", title="Artifact validation failed"),
        )

    mo.stop(
        inspection.schema_id != XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
        mo.callout(
            "This prototype is intentionally limited to the XJTU LSTM development "
            "artifact that records acquisition-aligned trajectories and feature residuals.",
            kind="danger",
            title="Unsupported evidence schema",
        ),
    )

    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    stage_by_name = {stage.name: stage for stage in inspection.stages}
    return artifact_path, document, inspection, stage_by_name


@app.cell
def _(document):
    feature_names = tuple(document["feature_schema"]["selected_features"])
    trajectories = {
        trajectory["asset_id"]: tuple(trajectory["observations"])
        for trajectory in document["scoring"]["trajectories"]
    }
    bearing_summaries = {
        bearing["asset_id"]: bearing for bearing in document["evaluation"]["bearings"]
    }
    return bearing_summaries, feature_names, trajectories


@app.cell
def _(bearing_summaries, mo):
    header = mo.md(
        """
        # Maintenance Evidence Review

        Can a maintenance engineer understand recorded anomaly evidence, its limits,
        and its provenance without turning retrospective experiment evidence into an
        operational diagnosis or maintenance decision?

        This read-only prototype consumes one version-controlled XJTU LSTM development
        artifact. It does not create asset status, alarms, fault diagnosis, maintenance
        priority, or RUL.
        """
    )
    bearing_selector = mo.ui.dropdown(
        options=list(bearing_summaries),
        value=next(iter(bearing_summaries)),
        label="Evidence scope / bearing",
    )
    view_selector = mo.ui.radio(
        options=["Evidence Summary", "Trend & Observations", "Limits & Provenance"],
        value="Evidence Summary",
        inline=True,
        label="Maintenance review view",
    )
    return bearing_selector, header, view_selector


@app.cell
def _(mo):
    def fact_value(stage, label):
        return next((fact.value for fact in stage.facts if fact.label == label), "unavailable")

    def facts_table(stage):
        rows = "\n".join(
            f"| {fact.label} | {str(fact.value).replace('|', '&#124;')} |" for fact in stage.facts
        )
        return mo.md("| Field | Recorded value |\n| --- | --- |\n" + rows)

    return fact_value, facts_table


@app.cell
def _(bearing_selector, bearing_summaries, trajectories):
    selected_bearing = bearing_selector.value
    selected_summary = bearing_summaries[selected_bearing]
    selected_observations = trajectories[selected_bearing]
    return selected_bearing, selected_observations, selected_summary


@app.cell
def _(
    artifact_path,
    fact_value,
    inspection,
    mo,
    selected_bearing,
    selected_summary,
    stage_by_name,
):
    _evaluation = stage_by_name["Evaluation"]
    _capability = stage_by_name["Capability"]
    _model = stage_by_name["Model"]

    _warning_text = "\n".join(
        f"- {warning}" for stage in inspection.stages for warning in stage.warnings
    )
    _warnings = (
        mo.callout(mo.md(_warning_text), kind="warn", title="Recorded evidence boundary")
        if _warning_text
        else mo.callout("No artifact warnings were recorded.", kind="success")
    )

    summary_view = mo.vstack(
        [
            mo.md("## Evidence Summary"),
            mo.callout(
                "This is retrospective development evidence for a selected validation bearing. "
                "It is not a live asset state and does not establish an alarm, fault class, "
                "maintenance priority, or remaining useful life.",
                kind="warn",
                title="Interpretation boundary",
            ),
            bearing_selector,
            mo.hstack(
                [
                    mo.stat(selected_bearing, label="Review target"),
                    mo.stat(
                        f"{selected_summary['score_window_count']:,}",
                        label="Scored windows",
                        caption="right-edge aligned",
                    ),
                    mo.stat(
                        f"{selected_summary['acquisition_order_spearman_rho']:.6f}",
                        label="Trajectory association",
                        caption="Spearman rho vs acquisition order",
                    ),
                    mo.stat(
                        f"{selected_summary['late_vs_middle_rank_probability']:.6f}",
                        label="Late-vs-middle evidence",
                        caption="retrospective lifecycle thirds",
                    ),
                ],
                widths="equal",
            ),
            mo.md(
                "### What this evidence can support\n\n"
                "- Review whether reconstruction mismatch changes over the recorded run.\n"
                "- Inspect which model input features show larger reconstruction residual.\n"
                "- Trace displayed values back to the experiment artifact and code provenance."
            ),
            mo.md(
                "### What this evidence cannot support\n\n"
                "- No thresholded normal/fault state.\n"
                "- No fault diagnosis or physical root-cause attribution.\n"
                "- No maintenance priority or recommended action.\n"
                "- No health indicator or RUL claim."
            ),
            mo.md(
                f"Model evidence uses **{fact_value(_model, 'Family')}** with "
                f"**{fact_value(_model, 'Score semantics')}** score semantics."
            ),
            _warnings,
            mo.md(
                "The full evaluation remains experiment-scoped. This role-specific view does "
                "not change the recorded evaluation or capability contract."
            ),
            mo.md(f"Evidence artifact: `{artifact_path}`"),
        ],
        gap=1.2,
    )
    return (summary_view,)


@app.cell
def _(
    feature_names,
    mo,
    plt,
    selected_bearing,
    selected_observations,
    selected_summary,
):
    _score_figure, _score_axis = plt.subplots(figsize=(11, 4.5))
    _score_axis.plot(
        [observation["acquisition_index"] for observation in selected_observations],
        [observation["score"] for observation in selected_observations],
        linewidth=1.2,
    )
    _score_axis.set_xlabel("Right-edge acquisition index")
    _score_axis.set_ylabel("Mean squared reconstruction error")
    _score_axis.set_title(f"{selected_bearing} recorded anomaly-evidence trajectory")
    _score_axis.grid(alpha=0.2)
    _score_figure.tight_layout()

    _residual_pairs = sorted(
        zip(feature_names, selected_summary["mean_feature_residuals"], strict=True),
        key=lambda pair: pair[1],
    )
    _residual_figure, _residual_axis = plt.subplots(figsize=(11, 6))
    _residual_axis.barh(
        [name.removeprefix("feature.") for name, _ in _residual_pairs],
        [value for _, value in _residual_pairs],
    )
    _residual_axis.set_xlabel("Mean squared residual in robust-scaled feature space")
    _residual_axis.set_title(f"{selected_bearing} recorded model residual evidence")
    _residual_axis.grid(axis="x", alpha=0.2)
    _residual_figure.tight_layout()

    _top_observations = sorted(
        selected_observations,
        key=lambda observation: observation["score"],
        reverse=True,
    )[:10]
    _top_rows = "\n".join(
        "| {index} | `{source}` | {score:.6f} |".format(
            index=observation["acquisition_index"],
            source=observation["source_observation_id"],
            score=observation["score"],
        )
        for observation in _top_observations
    )

    trend_view = mo.vstack(
        [
            mo.md("## Trend & Observations"),
            mo.callout(
                "Higher reconstruction score means larger model mismatch in this experiment. "
                "There is no validated alert threshold, so the plot must not be read as a "
                "normal/fault state chart.",
                kind="warn",
                title="Score semantics",
            ),
            _score_figure,
            mo.md(
                "The trajectory is acquisition-aligned retrospective evidence. A positive "
                "rank association with acquisition order does not prove monotonic degradation "
                "or identify a physical failure mechanism."
            ),
            mo.md(
                "### Highest recorded reconstruction scores\n\n"
                "| Acquisition | Source observation | Score |\n"
                "| ---: | --- | ---: |\n" + _top_rows
            ),
            _residual_figure,
            mo.callout(
                "Feature residuals describe reconstruction mismatch in robust-scaled model "
                "space. They are not physical fault contribution, causal attribution, or a "
                "diagnostic label.",
                kind="info",
                title="Supporting model evidence",
            ),
        ],
        gap=1.2,
    )
    return (trend_view,)


@app.cell
def _(artifact_path, facts_table, inspection, mo, selected_bearing, stage_by_name):
    _selected_warnings = [
        warning for stage in inspection.stages for warning in stage.warnings
    ]
    _warning_block = (
        mo.callout(
            mo.md("\n".join(f"- {warning}" for warning in _selected_warnings)),
            kind="warn",
            title="Experiment warnings",
        )
        if _selected_warnings
        else mo.callout("No artifact warnings were recorded.", kind="success")
    )

    limits_view = mo.vstack(
        [
            mo.md("## Limits & Provenance"),
            mo.md(f"Selected evidence scope: **{selected_bearing}**"),
            mo.md("### Recorded capability"),
            facts_table(stage_by_name["Capability"]),
            mo.md("### Evaluation context"),
            facts_table(stage_by_name["Evaluation"]),
            _warning_block,
            mo.md("### Provenance"),
            facts_table(stage_by_name["Provenance"]),
            mo.callout(
                "A future operational maintenance view will require real inference-time "
                "identity, observation time, data quality, validated state/threshold semantics, "
                "and deployment/model lineage. Those fields are not inferred from this "
                "retrospective experiment artifact.",
                kind="info",
                title="Operational-result boundary",
            ),
            mo.md(f"Evidence artifact: `{artifact_path}`"),
        ],
        gap=1.2,
    )
    return (limits_view,)


@app.cell
def _(header, limits_view, mo, summary_view, trend_view, view_selector):
    _views = {
        "Evidence Summary": summary_view,
        "Trend & Observations": trend_view,
        "Limits & Provenance": limits_view,
    }
    mo.vstack([header, view_selector, _views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
