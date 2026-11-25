import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import os
    from pathlib import Path

    import marimo as mo

    from industrial_phm.experiments.result_inspection import (
        ExperimentResultInspectionError,
        inspect_experiment_result,
    )

    return (
        ExperimentResultInspectionError,
        Path,
        inspect_experiment_result,
        mo,
        os,
    )


@app.cell
def _(mo, os):
    _artifact_options = {
        "XJTU Isolation Forest holdout": (
            "docs/research/results/xjtu-sy-iforest-fold-1-holdout-v1.json"
        ),
        "IMS Isolation Forest cross-test": (
            "docs/research/results/ims-bearings-iforest-single-channel-cross-test-v1.json"
        ),
    }
    _default_artifact = os.environ.get(
        "INDUSTRIAL_PHM_WORKBENCH_ARTIFACT",
        _artifact_options["XJTU Isolation Forest holdout"],
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
    return artifact_path, inspection


@app.cell
def _(inspection):
    stage_by_name = {stage.name: stage for stage in inspection.stages}
    return (stage_by_name,)


@app.cell
def _(mo, stage_by_name):
    view_selector = mo.ui.radio(
        options=["Experiment Overview", "Pipeline Lineage", "Evidence Explorer"],
        value="Experiment Overview",
        inline=True,
        label="View",
    )
    stage_selector = mo.ui.dropdown(
        options=list(stage_by_name),
        value=next(iter(stage_by_name)),
        label="Pipeline stage",
    )
    return stage_selector, view_selector


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
        ],
        gap=1.2,
    )
    return (lineage_view,)


@app.cell
def _(artifact_path, facts_table, mo, stage_by_name):
    evidence_view = mo.vstack(
        [
            mo.md("## Evidence Explorer"),
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
