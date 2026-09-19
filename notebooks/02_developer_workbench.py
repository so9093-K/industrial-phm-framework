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
def _(mo):
    artifact_input = mo.ui.text(
        value="docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json",
        label="Canonical experiment artifact",
        full_width=True,
    )
    mo.vstack(
        [
            mo.md(
                """
                # Developer Workbench

                Review one validated experiment through a shared **Experiment Overview**,
                **Pipeline Lineage**, and **Evidence Explorer** context. This prototype is a
                read-only research interface; the repository artifact remains the Source of Truth.
                """
            ),
            artifact_input,
        ]
    )
    return (artifact_input,)


@app.cell
def _(
    ExperimentResultInspectionError,
    Path,
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
    artifact_input,
    inspect_experiment_result,
    json,
    mo,
):
    artifact_path = Path(artifact_input.value)
    mo.stop(
        not artifact_path.is_file(),
        mo.callout(
            f"Canonical experiment artifact was not found: `{artifact_path}`",
            kind="warn",
            title="Artifact unavailable",
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
            "The first Workbench prototype supports the validated XJTU LSTM development "
            f"schema, not `{inspection.schema_id}`.",
            kind="warn",
            title="Evidence view unavailable",
        ),
    )
    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    return artifact_path, document, inspection


@app.cell
def _(document, inspection):
    stage_by_name = {stage.name: stage for stage in inspection.stages}
    provenance = document["provenance"]
    feature_names = tuple(document["feature_schema"]["selected_features"])
    trajectories = {
        trajectory["asset_id"]: tuple(trajectory["observations"])
        for trajectory in document["scoring"]["trajectories"]
    }
    bearing_summaries = {
        bearing["asset_id"]: bearing for bearing in document["evaluation"]["bearings"]
    }
    return bearing_summaries, feature_names, provenance, stage_by_name, trajectories


@app.cell
def _(bearing_summaries, mo, stage_by_name):
    view_selector = mo.ui.radio(
        options=["Experiment Overview", "Pipeline Lineage", "Evidence Explorer"],
        value="Experiment Overview",
        inline=True,
        label="View",
    )
    bearing_selector = mo.ui.dropdown(
        options=list(bearing_summaries),
        value=next(iter(bearing_summaries)),
        label="Validation bearing",
    )
    stage_selector = mo.ui.dropdown(
        options=list(stage_by_name),
        value="Sequence Construction",
        label="Pipeline stage",
    )
    return bearing_selector, stage_selector, view_selector


@app.cell
def _(mo):
    def fact_value(stage, label):
        return next((fact.value for fact in stage.facts if fact.label == label), "unavailable")

    def facts_table(stage):
        rows = "\n".join(
            f"| {fact.label} | {str(fact.value).replace('|', '&#124;')} |" for fact in stage.facts
        )
        return mo.md("| Field | Effective value |\n| --- | --- |\n" + rows)

    return fact_value, facts_table


@app.cell
def _(artifact_path, fact_value, facts_table, inspection, mo, stage_by_name):
    _source = stage_by_name["Source"]
    _population = stage_by_name["Population"]
    _model = stage_by_name["Model"]
    _evaluation = stage_by_name["Evaluation"]
    _capability = stage_by_name["Capability"]
    _provenance = stage_by_name["Provenance"]

    _warning_text = "\n".join(
        f"- {warning}" for stage in inspection.stages for warning in stage.warnings
    )
    _warnings = (
        mo.callout(mo.md(_warning_text), kind="warn", title="Evidence boundary")
        if _warning_text
        else mo.callout("No artifact warnings.", kind="success")
    )
    overview_view = mo.vstack(
        [
            mo.md("## Experiment Overview"),
            mo.hstack(
                [
                    mo.stat(inspection.status, label="Status"),
                    mo.stat(fact_value(_source, "Dataset"), label="Dataset"),
                    mo.stat(fact_value(_model, "Family"), label="Model"),
                    mo.stat(fact_value(_model, "Random seed"), label="Random seed"),
                ],
                widths="equal",
            ),
            mo.md("### Population summary"),
            facts_table(_population),
            mo.md("### Evaluation summary"),
            facts_table(_evaluation),
            mo.md("### Capability"),
            facts_table(_capability),
            _warnings,
            mo.md("### Provenance"),
            facts_table(_provenance),
            mo.md(f"Canonical artifact: `{artifact_path}`"),
        ],
        gap=1.2,
    )
    return (overview_view,)


@app.cell
def _(facts_table, inspection, mo, stage_by_name, stage_selector):
    _selected_stage = stage_by_name[stage_selector.value]
    _flow = " → ".join(f"**{stage.name}**" for stage in inspection.stages)
    _stage_rows = "\n".join(
        f"| {index} | {stage.name} | {stage.status} | {len(stage.facts)} |"
        for index, stage in enumerate(inspection.stages, start=1)
    )
    _stage_warnings = (
        mo.callout(
            mo.md("\n".join(f"- {warning}" for warning in _selected_stage.warnings)),
            kind="warn",
            title=f"{_selected_stage.name} warnings",
        )
        if _selected_stage.warnings
        else mo.callout(
            "No warnings recorded for this stage.",
            kind="success",
            title=f"{_selected_stage.name} validation",
        )
    )
    lineage_view = mo.vstack(
        [
            mo.md("## Pipeline Lineage"),
            mo.md(_flow),
            mo.md(
                "| Order | Stage | Status | Facts |\n| ---: | --- | --- | ---: |\n" + _stage_rows
            ),
            stage_selector,
            mo.md(f"### {_selected_stage.name}"),
            facts_table(_selected_stage),
            _stage_warnings,
            mo.callout(
                "Acquisition, observation, and window counts retain their declared units. "
                "Sequence Construction records the acquisition-to-window transition and "
                "dropped prefix population without treating both units as interchangeable.",
                kind="info",
                title="Population units",
            ),
        ],
        gap=1.2,
    )
    return (lineage_view,)


@app.cell
def _(
    artifact_path,
    bearing_selector,
    bearing_summaries,
    feature_names,
    mo,
    plt,
    provenance,
    trajectories,
):
    selected_bearing = bearing_selector.value
    selected_observations = trajectories[selected_bearing]
    selected_summary = bearing_summaries[selected_bearing]

    _score_figure, _score_axis = plt.subplots(figsize=(11, 4.5))
    _score_axis.plot(
        [observation["acquisition_index"] for observation in selected_observations],
        [observation["score"] for observation in selected_observations],
        color="#2563eb",
        linewidth=1.2,
    )
    _score_axis.set_xlabel("Right-edge acquisition index")
    _score_axis.set_ylabel("Mean squared reconstruction error")
    _score_axis.set_title(f"{selected_bearing} acquisition-aligned anomaly-score trajectory")
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
        color="#ea580c",
    )
    _residual_axis.set_xlabel("Mean squared residual in robust-scaled feature space")
    _residual_axis.set_title(f"{selected_bearing} per-feature reconstruction residual")
    _residual_axis.grid(axis="x", alpha=0.2)
    _residual_figure.tight_layout()

    _top_observations = sorted(
        selected_observations,
        key=lambda observation: observation["score"],
        reverse=True,
    )[:10]
    _top_rows = "\n".join(
        "| {index} | `{source}` | `{window}` | {score:.6f} |".format(
            index=observation["acquisition_index"],
            source=observation["source_observation_id"],
            window=observation["window_id"],
            score=observation["score"],
        )
        for observation in _top_observations
    )

    evidence_view = mo.vstack(
        [
            mo.md("## Evidence Explorer"),
            bearing_selector,
            mo.hstack(
                [
                    mo.stat(
                        f"{selected_summary['score_window_count']:,}",
                        label="Scored windows",
                        caption="right-edge aligned",
                    ),
                    mo.stat(
                        f"{selected_summary['acquisition_order_spearman_rho']:.6f}",
                        label="Spearman rho",
                        caption="acquisition order",
                    ),
                    mo.stat(
                        f"{selected_summary['late_vs_middle_rank_probability']:.6f}",
                        label="Late-vs-middle",
                        caption="retrospective lifecycle thirds",
                    ),
                    mo.stat(
                        f"{selected_summary['dropped_prefix_count']:,}",
                        label="Dropped prefix",
                        caption="acquisitions",
                    ),
                ],
                widths="equal",
            ),
            mo.callout(
                "Scores are higher-is-more-anomalous and aligned to each window's right-edge "
                "acquisition. No threshold, normal/fault state, health assessment, diagnosis, "
                "or RUL is defined by this result.",
                kind="warn",
                title="Score semantics and unsupported capability",
            ),
            _score_figure,
            mo.md(
                "The lifecycle statistic is retrospective development evidence. The trajectory "
                "must be inspected directly; a positive rank correlation does not assert "
                "monotonic degradation."
            ),
            _residual_figure,
            mo.md(
                "Per-feature values are reconstruction mismatch in the robust-scaled model "
                "space. They are model evidence, not physical fault contribution or causal "
                "attribution."
            ),
            mo.md(
                "### Highest-score observations in the selected bearing\n\n"
                "| Acquisition | Source observation | Window | Score |\n"
                "| ---: | --- | --- | ---: |\n" + _top_rows
            ),
            mo.md(
                f"""
                **Experiment:** `{provenance["experiment_id"]}`<br>
                **Declared code revision:** `{provenance["code_revision"]}`<br>
                **Canonical artifact:** `{artifact_path}`
                """
            ),
        ],
        gap=1.2,
    )
    return (evidence_view,)


@app.cell
def _(evidence_view, lineage_view, mo, overview_view, view_selector):
    _views = {
        "Experiment Overview": overview_view,
        "Pipeline Lineage": lineage_view,
        "Evidence Explorer": evidence_view,
    }
    mo.vstack([view_selector, _views[view_selector.value]], gap=1.5)
    return


if __name__ == "__main__":
    app.run()
