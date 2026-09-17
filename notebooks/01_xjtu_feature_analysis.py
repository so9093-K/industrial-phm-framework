import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    from collections import defaultdict
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt

    from industrial_phm.experiments.xjtu_characterization_artifacts import (
        XjtuCharacterizationArtifactError,
        load_xjtu_characterization_artifacts,
    )

    return (
        Path,
        XjtuCharacterizationArtifactError,
        defaultdict,
        load_xjtu_characterization_artifacts,
        mo,
        plt,
    )


@app.cell
def _(mo):
    artifact_dir_input = mo.ui.text(
        value="data/processed/xjtu-sy/vibration-statistical-v1-characterization",
        label="Characterization artifact directory",
        full_width=True,
    )
    mo.vstack(
        [
            mo.md(
                """
                # XJTU-SY interactive feature analysis

                This spike is fixed to the current `fold-1/train` development scope.
                It consumes generated characterization artifacts and does not expose holdout-test data.
                """
            ),
            artifact_dir_input,
        ]
    )
    return (artifact_dir_input,)


@app.cell
def _(
    Path,
    XjtuCharacterizationArtifactError,
    artifact_dir_input,
    load_xjtu_characterization_artifacts,
    mo,
):
    artifact_dir = Path(artifact_dir_input.value)
    _feature_table = artifact_dir / "vibration-statistical-v1-fold-1-train-features.csv"
    _summary = artifact_dir / "xjtu-feature-characterization-summary-v1-fold-1-train.json"

    mo.stop(
        not _feature_table.is_file() or not _summary.is_file(),
        mo.md(
            f"""
            Characterization artifacts are missing from `{artifact_dir}`.

            Generate the current `fold-1/train` characterization result first.
            """
        ),
    )

    try:
        characterization = load_xjtu_characterization_artifacts(_feature_table, _summary)
    except XjtuCharacterizationArtifactError as error:
        mo.stop(True, mo.md(f"Characterization artifacts could not be loaded: `{error}`"))

    return artifact_dir, characterization


@app.cell
def _(characterization, mo):
    _default_feature = (
        "feature.Horizontal_vibration_signals.rms"
        if "feature.Horizontal_vibration_signals.rms" in characterization.feature_names
        else characterization.feature_names[0]
    )
    condition_selector = mo.ui.dropdown(
        options=["All", *characterization.operating_conditions],
        value="All",
        label="Operating condition",
    )
    feature_selector = mo.ui.dropdown(
        options=list(characterization.feature_names),
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
def _(characterization, condition_selector, mo):
    if condition_selector.value == "All":
        _asset_options = characterization.asset_ids
    else:
        _asset_options = tuple(
            sorted(
                {
                    record.asset_id
                    for record in characterization.records
                    if record.operating_condition == condition_selector.value
                }
            )
        )

    bearing_selector = mo.ui.dropdown(
        options=["All", *_asset_options],
        value="All",
        label="Bearing run",
    )
    return (bearing_selector,)


@app.cell
def _(
    artifact_dir,
    bearing_selector,
    characterization,
    condition_selector,
    feature_selector,
    mo,
    x_axis_selector,
):
    mo.vstack(
        [
            mo.md(
                f"""
                **Development scope:** `{characterization.split_id}` / `{characterization.fold_id}` /
                `{characterization.partition}`  
                **Feature set:** `{characterization.feature_set_id}`  
                **Artifacts:** `{artifact_dir}`
                """
            ),
            mo.hstack(
                [condition_selector, bearing_selector, feature_selector, x_axis_selector],
                widths="equal",
            ),
        ]
    )
    return


@app.cell
def _(bearing_selector, characterization, condition_selector):
    selected_records = tuple(
        record
        for record in characterization.records
        if (
            condition_selector.value == "All"
            or record.operating_condition == condition_selector.value
        )
        and (bearing_selector.value == "All" or record.asset_id == bearing_selector.value)
    )
    return (selected_records,)


@app.cell
def _(
    bearing_selector,
    characterization,
    condition_selector,
    feature_selector,
    mo,
    selected_records,
):
    mo.md(
        f"""
        **Selected feature:** `{feature_selector.value}`  
        **Operating condition:** `{condition_selector.value}`  
        **Bearing run:** `{bearing_selector.value}`  
        **Visible acquisitions:** `{len(selected_records)}` / `{len(characterization.records)}`
        """
    )
    return


@app.cell
def _(
    characterization,
    defaultdict,
    feature_selector,
    mo,
    plt,
    selected_records,
    x_axis_selector,
):
    mo.stop(not selected_records, mo.md("No acquisitions match the current selection."))
    _feature_index = characterization.feature_names.index(feature_selector.value)

    _by_asset = defaultdict(list)
    for _record in selected_records:
        _by_asset[_record.asset_id].append(_record)

    _figure, _axis = plt.subplots(figsize=(10, 5))
    for _asset_id, _records in sorted(_by_asset.items()):
        _ordered = sorted(_records, key=lambda record: record.acquisition_index)
        if x_axis_selector.value == "Acquisition index":
            _x_values = [record.acquisition_index for record in _ordered]
            _x_label = "Acquisition index"
        else:
            _final_index = _ordered[-1].acquisition_index
            _x_values = [record.acquisition_index / _final_index for record in _ordered]
            _x_label = "Retrospective lifecycle fraction"

        _axis.plot(
            _x_values,
            [record.values[_feature_index] for record in _ordered],
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
        The retrospective lifecycle fraction uses each run's known final acquisition count.
        It is for retrospective visualization only and must not be used as an online model input.

        UI state is exploratory analysis state, not a feature-selection decision or experiment
        configuration.
        """
        if x_axis_selector.value == "Retrospective lifecycle fraction"
        else ""
    )
    return


if __name__ == "__main__":
    app.run()
