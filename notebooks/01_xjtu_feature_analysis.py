import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    from collections import defaultdict
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt

    from industrial_phm.experiments.xjtu_feature_analysis import (
        XjtuFeatureAnalysisError,
        load_xjtu_feature_analysis,
    )

    return Path, XjtuFeatureAnalysisError, defaultdict, load_xjtu_feature_analysis, mo, plt


@app.cell
def _(Path, XjtuFeatureAnalysisError, load_xjtu_feature_analysis, mo):
    artifact_dir = Path("data/processed/xjtu-sy/vibration-statistical-v1-characterization")
    _feature_table_path = artifact_dir / "vibration-statistical-v1-fold-1-train-features.csv"
    _summary_path = artifact_dir / "xjtu-feature-characterization-summary-v1-fold-1-train.json"

    mo.stop(
        not _feature_table_path.is_file() or not _summary_path.is_file(),
        mo.md(
            f"""
            ## XJTU-SY interactive feature analysis

            `fold-1/train` characterization artifacts are required before this notebook can run.

            Expected directory: `{artifact_dir}`
            """
        ),
    )

    try:
        analysis = load_xjtu_feature_analysis(_feature_table_path, _summary_path)
    except XjtuFeatureAnalysisError as error:
        mo.stop(True, mo.md(f"Characterization artifacts could not be loaded: `{error}`"))

    return analysis, artifact_dir


@app.cell
def _(analysis, mo):
    _default_feature = (
        "feature.Horizontal_vibration_signals.rms"
        if "feature.Horizontal_vibration_signals.rms" in analysis.feature_names
        else analysis.feature_names[0]
    )
    condition_selector = mo.ui.dropdown(
        options=["All", *analysis.operating_conditions],
        value="All",
        label="Operating condition",
    )
    feature_selector = mo.ui.dropdown(
        options=list(analysis.feature_names),
        value=_default_feature,
        label="Feature",
    )
    x_axis_selector = mo.ui.dropdown(
        options=["Acquisition index", "Retrospective lifecycle fraction"],
        value="Acquisition index",
        label="X axis",
    )
    return condition_selector, feature_selector, x_axis_selector


@app.cell
def _(analysis, condition_selector, mo):
    if condition_selector.value == "All":
        _asset_options = analysis.asset_ids
    else:
        _asset_options = tuple(
            sorted(
                {
                    record.asset_id
                    for record in analysis.records
                    if record.operating_condition == condition_selector.value
                }
            )
        )

    bearing_selector = mo.ui.dropdown(
        options=["All", *_asset_options],
        value="All",
        label="Bearing run",
    )
    return bearing_selector


@app.cell
def _(
    analysis,
    artifact_dir,
    bearing_selector,
    condition_selector,
    feature_selector,
    mo,
    x_axis_selector,
):
    mo.vstack(
        [
            mo.md(
                f"""
                # XJTU-SY interactive feature analysis

                Development scope: `{analysis.split_id}` / `{analysis.fold_id}` /
                `{analysis.partition}`  
                Feature set: `{analysis.feature_set_id}`  
                Artifacts: `{artifact_dir}`

                This view consumes generated characterization artifacts only. It does not parse
                raw waveform files, recompute features, or expose the holdout test partition.
                """
            ),
            mo.hstack(
                [
                    condition_selector,
                    bearing_selector,
                    feature_selector,
                    x_axis_selector,
                ]
            ),
        ]
    )
    return


@app.cell
def _(analysis, bearing_selector, condition_selector, feature_selector):
    _selected_condition = None if condition_selector.value == "All" else condition_selector.value
    _selected_assets = None if bearing_selector.value == "All" else (bearing_selector.value,)
    selected_points = analysis.feature_series(
        feature_selector.value,
        operating_condition=_selected_condition,
        asset_ids=_selected_assets,
    )
    return (selected_points,)


@app.cell
def _(analysis, bearing_selector, condition_selector, feature_selector, mo, selected_points):
    mo.md(
        f"""
        **Selected feature:** `{feature_selector.value}`  
        **Operating condition:** `{condition_selector.value}`  
        **Bearing run:** `{bearing_selector.value}`  
        **Visible acquisitions:** `{len(selected_points)}` / `{len(analysis.records)}`
        """
    )
    return


@app.cell
def _(defaultdict, feature_selector, mo, plt, selected_points, x_axis_selector):
    mo.stop(not selected_points, mo.md("No acquisitions match the current selection."))

    _by_asset = defaultdict(list)
    for _point in selected_points:
        _by_asset[_point.asset_id].append(_point)

    _figure, _axis = plt.subplots(figsize=(10, 5))
    for _asset_id, _points in sorted(_by_asset.items()):
        _ordered = sorted(_points, key=lambda point: point.acquisition_index)
        if x_axis_selector.value == "Acquisition index":
            _x_values = [point.acquisition_index for point in _ordered]
            _x_label = "Acquisition index"
        else:
            _x_values = [point.retrospective_lifecycle_fraction for point in _ordered]
            _x_label = "Retrospective lifecycle fraction"
        _axis.plot(
            _x_values,
            [point.value for point in _ordered],
            label=_asset_id,
        )

    _axis.set_xlabel(_x_label)
    _axis.set_ylabel(feature_selector.value)
    _axis.set_title("Feature trajectory by bearing run")
    if len(_by_asset) > 1:
        _axis.legend()
    _figure.tight_layout()
    mo.vstack([_figure])
    return


@app.cell
def _(mo, x_axis_selector):
    mo.md(
        """
        ### Interpretation boundary

        The retrospective lifecycle fraction uses each run's known final acquisition count.
        It is for retrospective visualization only and must not be used as an online model input.

        This notebook is an interactive analysis spike. Observations made here can motivate
        additional reusable characterization calculations, but UI state is not an experiment
        configuration or feature-selection decision.
        """
        if x_axis_selector.value == "Retrospective lifecycle fraction"
        else ""
    )
    return


if __name__ == "__main__":
    app.run()
