from datetime import UTC, datetime
from pathlib import Path

import pytest

from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.demo.bearing import ASSET, COUNT, STABLE, prepare_bearing_demo
from industrial_phm.models.package import EstimatorKind, load_model_package
from industrial_phm.runtime import OperationsWorkspace
from industrial_phm.runtime.operations_demo_context import (
    order_by_exceedance,
    read_bearing_journey,
)


def test_bearing_example_scores_independent_streams_with_real_estimators_and_resumes(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    started_at = datetime.now(UTC)
    workspace = prepare_bearing_demo(tmp_path / "example")
    context = read_bearing_journey(workspace.root)
    assert context is not None and context["dataset"] == "synthetic"
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    bindings = store.list_bindings()
    assert len(bindings) == 4
    kinds = set()
    for binding in bindings:
        package = load_model_package(workspace.models_path / binding.package_id)
        kinds.add(package.manifest.estimator_kind)
        assert package.manifest.training_scope["asset_ids"] == ["reference"]
        result = store.get_result(binding.binding_id, COUNT)
        assert result is not None and result.state.value == "analyzed"
        assert result.processed_at >= started_at
        assert result.output["exceeds_threshold"] is (binding.asset_id == ASSET)
        if binding.asset_id == STABLE:
            assert binding.binding_id not in context["bindings"]
        if package.manifest.estimator_kind is EstimatorKind.LSTM_AUTOENCODER:
            assert store.get_result(binding.binding_id, 1).state.value == "skipped"
    assert kinds == {EstimatorKind.ISOLATION_FOREST_REFIT, EstimatorKind.LSTM_AUTOENCODER}
    # The guide opens first a model whose latest stored score is over its own threshold.
    assert order_by_exceedance(workspace.root, context) == context
    below = next(b.binding_id for b in bindings if b.asset_id == STABLE)
    over = context["bindings"][1]
    mixed = {**context, "bindings": [below, over]}
    assert order_by_exceedance(workspace.root, mixed)["bindings"] == [over, below]
    latest = {b.binding_id: store.get_result(b.binding_id, COUNT) for b in bindings}
    prepare_bearing_demo(workspace.root)
    assert latest == {b.binding_id: store.get_result(b.binding_id, COUNT) for b in bindings}


def test_example_never_adopts_a_real_workspace_or_unbounded_context(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    with pytest.raises(ValueError, match="new or previously prepared"):
        prepare_bearing_demo(root)
    workspace = OperationsWorkspace(root)
    workspace.web_context_path.parent.mkdir(parents=True)
    workspace.web_context_path.write_text("x" * 8193)
    assert read_bearing_journey(root) is None
    # Without stored scores the prepared order stays; reading never creates a store.
    unscored = {"bindings": ["first", "second"]}
    assert order_by_exceedance(root, unscored) == unscored
    assert not workspace.phm_analysis_path.exists()
