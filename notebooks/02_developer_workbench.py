import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    import os
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
        os,
        plt,
    )


@app.cell
def _(mo, os):
    _artifact_options = {
        "XJTU LSTM development": (
            "docs/research/results/xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
        ),
        "XJTU Isolation Forest holdout": (
            "docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json"
        ),
        "IMS Isolation Forest cross-test": (
            "docs/research/results/ims-bearings-iforest-single-channel-cross-test-v1.json"
        ),
    }
    _default_artifact = os.environ.get(
        "INDUSTRIAL_PHM_WORKBENCH_ARTIFACT",
        _artifact_options["XJTU LSTM development"],
    )
    if _default_artifact not in _artifact_options.values():
        raise ValueError(
            "INDUSTRIAL_PHM_WORKBENCH_ARTIFACT must identify a supported evidence artifact"
        )
    _default_label = next(
        label for label, path in _artifact_options.items() if path == _default_artifact
    )
    artifact_input = mo.ui.dropdown(
        options=_artifact_options,
        value=_default_label,
        label="Version-controlled evidence artifact",
        searchable=True,
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
    artifact_input,
    inspect_experiment_result,
    json,
    mo,
):
    artifact_path = Path(artifact_input.value)
    mo.stop(
        not artifact_path.is_file(),
        mo.callout(
            f"Version-controlled evidence artifact was not found: `{artifact_path}`",
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

    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    return artifact_path, document, inspection


@app.cell
def _(XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID, document, inspection):
    stage_by_name = {stage.name: stage for stage in inspection.stages}
    detailed_evidence_status = (
        "available"
        if inspection.schema_id == XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID
        else "not recorded"
    )
    if detailed_evidence_status == "available":
        feature_names = tuple(document["feature_schema"]["selected_features"])
        trajectories = {
            trajectory["asset_id"]: tuple(trajectory["observations"])
            for trajectory in document["scoring"]["trajectories"]
        }
        bearing_summaries = {
            bearing["asset_id"]: bearing for bearing in document["evaluation"]["bearings"]
        }
    else:
        feature_names = ()
        trajectories = {}
        bearing_summaries = {}
    return (
        bearing_summaries,
        detailed_evidence_status,
        feature_names,
        stage_by_name,
        trajectories,
    )


@app.cell
def _(bearing_summaries, detailed_evidence_status, mo, stage_by_name):
    view_selector = mo.ui.radio(
        options=["Experiment Overview", "Pipeline Lineage", "Evidence Explorer"],
        value="Experiment Overview",
        inline=True,
        label="View",
    )
    _bearing_options = (
        list(bearing_summaries) if detailed_evidence_status == "available" else ["not recorded"]
    )
    bearing_selector = mo.ui.dropdown(
        options=_bearing_options,
        value=_bearing_options[0],
        label="Validation bearing",
        disabled=detailed_evidence_status != "available",
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
            mo.md(f"Evidence artifact: `{artifact_path}`"),
        ],
        gap=1.2,
    )
    return (overview_view,)


@app.cell
def _(facts_table, inspection, mo, stage_by_name, stage_selector):
    _selected_stage = stage_by_name[stage_selector.value]
    _sequence_stage = stage_by_name["Sequence Construction"]
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
    _population_unit_note = (
        "This model consumes acquisition-level feature observations. Sequence Construction "
        "is explicitly not applicable, so no window population is inferred."
        if _sequence_stage.status == "not applicable"
        else "Sequence Construction records the acquisition-to-window transition and dropped "
        "prefix population. Acquisition and window counts retain their declared units."
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
                _population_unit_note,
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
    detailed_evidence_status,
    facts_table,
    feature_names,
    mo,
    plt,
    stage_by_name,
    trajectories,
):
    if detailed_evidence_status == "available":
        _selected_bearing = bearing_selector.value
        _selected_observations = trajectories[_selected_bearing]
        _selected_summary = bearing_summaries[_selected_bearing]

        _score_figure, _score_axis = plt.subplots(figsize=(11, 4.5))
        _score_axis.plot(
            [observation["acquisition_index"] for observation in _selected_observations],
            [observation["score"] for observation in _selected_observations],
            color="#2563eb",
            linewidth=1.2,
        )
        _score_axis.set_xlabel("Right-edge acquisition index")
        _score_axis.set_ylabel("Mean squared reconstruction error")
        _score_axis.set_title(f"{_selected_bearing} acquisition-aligned anomaly-score trajectory")
        _score_axis.grid(alpha=0.2)
        _score_figure.tight_layout()

        _residual_pairs = sorted(
            zip(feature_names, _selected_summary["mean_feature_residuals"], strict=True),
            key=lambda pair: pair[1],
        )
        _residual_figure, _residual_axis = plt.subplots(figsize=(11, 6))
        _residual_axis.barh(
            [name.removeprefix("feature.") for name, _ in _residual_pairs],
            [value for _, value in _residual_pairs],
            color="#ea580c",
        )
        _residual_axis.set_xlabel("Mean squared residual in robust-scaled feature space")
        _residual_axis.set_title(f"{_selected_bearing} per-feature reconstruction residual")
        _residual_axis.grid(axis="x", alpha=0.2)
        _residual_figure.tight_layout()

        _top_observations = sorted(
            _selected_observations,
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
                mo.stat("available", label="Detailed evidence"),
                bearing_selector,
                mo.hstack(
                    [
                        mo.stat(
                            f"{_selected_summary['score_window_count']:,}",
                            label="Scored windows",
                            caption="right-edge aligned",
                        ),
                        mo.stat(
                            f"{_selected_summary['acquisition_order_spearman_rho']:.6f}",
                            label="Spearman rho",
                            caption="acquisition order",
                        ),
                        mo.stat(
                            f"{_selected_summary['late_vs_middle_rank_probability']:.6f}",
                            label="Late-vs-middle",
                            caption="retrospective lifecycle thirds",
                        ),
                        mo.stat(
                            f"{_selected_summary['dropped_prefix_count']:,}",
                            label="Dropped prefix",
                            caption="acquisitions",
                        ),
                    ],
                    widths="equal",
                ),
                mo.callout(
                    "Scores are higher-is-more-anomalous and aligned to each window's "
                    "right-edge acquisition. Thresholded state detection, health assessment, "
                    "diagnosis, and RUL remain unsupported by this result.",
                    kind="warn",
                    title="Score semantics and capability boundary",
                ),
                _score_figure,
                mo.md(
                    "The lifecycle statistic is retrospective development evidence. The "
                    "trajectory must be inspected directly; a positive rank correlation does "
                    "not assert monotonic degradation."
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
                mo.md("### Provenance"),
                facts_table(stage_by_name["Provenance"]),
                mo.md(f"Evidence artifact: `{artifact_path}`"),
            ],
            gap=1.2,
        )
    else:
        evidence_view = mo.vstack(
            [
                mo.md("## Evidence Explorer"),
                mo.stat("not recorded", label="Detailed evidence"),
                mo.callout(
                    "This result records validated aggregate evaluation evidence but does not "
                    "record acquisition-aligned raw trajectories or per-feature residuals. "
                    "The Workbench preserves that artifact boundary instead of deriving missing "
                    "evidence.",
                    kind="info",
                    title="Detailed evidence availability",
                ),
                mo.md("### Recorded evaluation"),
                facts_table(stage_by_name["Evaluation"]),
                mo.md("### Capability"),
                facts_table(stage_by_name["Capability"]),
                mo.md("### Provenance"),
                facts_table(stage_by_name["Provenance"]),
                mo.md(f"Evidence artifact: `{artifact_path}`"),
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
