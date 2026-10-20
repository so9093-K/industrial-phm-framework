import json
from pathlib import Path

import pytest

from industrial_phm.demo.xjtu_models import (
    IFOREST_RECIPE,
    LSTM_RECIPE,
    XjtuModelDemoConfig,
    existing_packages,
    prepare_xjtu_model_demo,
)


def test_a_bearing_the_models_were_fitted_on_is_refused(tmp_path: Path) -> None:
    # Scoring a train bearing would show the models' own training data as unseen behaviour.
    with pytest.raises(ValueError, match="not trained on"):
        prepare_xjtu_model_demo(
            XjtuModelDemoConfig(source=tmp_path, workspace=tmp_path / "ws", bearing="Bearing1_3")
        )
    assert not (tmp_path / "ws").exists()


def test_a_run_cut_too_short_for_an_outlook_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 20"):
        prepare_xjtu_model_demo(
            XjtuModelDemoConfig(source=tmp_path, workspace=tmp_path / "ws", until=10)
        )


def test_packages_already_in_the_workspace_are_reused_newest_first(tmp_path: Path) -> None:
    def package(name: str, recipe: str, created: str) -> None:
        (tmp_path / name).mkdir()
        (tmp_path / name / "package.json").write_text(
            json.dumps({"recipe_id": recipe, "created_at": created}), encoding="utf-8"
        )

    package("iforest-old", IFOREST_RECIPE, "2026-10-01T00:00:00+00:00")
    package("iforest-new", IFOREST_RECIPE, "2026-10-13T00:00:00+00:00")
    package("lstm", LSTM_RECIPE, "2026-10-13T00:00:00+00:00")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "package.json").write_text("{", encoding="utf-8")

    assert existing_packages(tmp_path) == {IFOREST_RECIPE: "iforest-new", LSTM_RECIPE: "lstm"}
    assert existing_packages(tmp_path / "missing") == {}
