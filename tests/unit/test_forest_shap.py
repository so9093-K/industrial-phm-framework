"""Path-dependent TreeSHAP parts of an Isolation Forest score (ADR-0035)."""

from __future__ import annotations

import itertools
import math

import numpy as np
from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

from industrial_phm.models.forest_shap import ForestShap, average_path_length


def _expected_length(tree: object, features: np.ndarray, row: np.ndarray, known: set[int]) -> float:
    """The tree's path length when only ``known`` features follow the row (TreeSHAP's game)."""
    nodes = tree.tree_  # type: ignore[attr-defined]
    counts = nodes.n_node_samples
    leaf_length = average_path_length(counts)

    def walk(node: int, depth: int) -> float:
        left, right = nodes.children_left[node], nodes.children_right[node]
        if left == -1:
            return depth + float(leaf_length[node])
        feature = int(features[nodes.feature[node]])
        if feature in known:
            goes_left = np.float32(row[feature]) <= nodes.threshold[node]
            return walk(left if goes_left else right, depth + 1)
        return (counts[left] * walk(left, depth + 1) + counts[right] * walk(right, depth + 1)) / (
            counts[node]
        )

    return walk(0, 0)


def test_parts_are_the_exact_shapley_values_of_each_trees_path_length() -> None:
    rng = np.random.default_rng(0)
    width = 5
    forest = IsolationForest(n_estimators=4, max_samples=32, max_features=0.8, random_state=1)
    forest.fit(rng.normal(size=(300, width)))
    rows = np.vstack([rng.normal(size=(4, width)), [[4.0, 0.0, 0.0, -3.0, 0.0]]])
    parts = ForestShap(forest, width).parts(rows)
    for row, got in zip(rows, parts, strict=True):
        exact = np.zeros(width)
        for tree, features in zip(forest.estimators_, forest.estimators_features_, strict=True):
            for player in range(width):
                others = [f for f in range(width) if f != player]
                for size in range(width):
                    weight = (
                        math.factorial(size)
                        * math.factorial(width - size - 1)
                        / math.factorial(width)
                    )
                    for known in itertools.combinations(others, size):
                        with_player = _expected_length(tree, features, row, {*known, player})
                        without = _expected_length(tree, features, row, set(known))
                        exact[player] += weight * (with_player - without)
        # A part is the shortening of the path, averaged over trees: positive raised the score.
        assert np.allclose(got, -exact / len(forest.estimators_), atol=1e-12)


def test_parts_add_up_to_the_path_the_forest_scores_by() -> None:
    rng = np.random.default_rng(3)
    forest = IsolationForest(n_estimators=100, max_samples=256, random_state=42)
    forest.fit(rng.normal(size=(700, 12)))
    explain = ForestShap(forest, 12)
    rows = np.vstack([rng.normal(size=(20, 12)), np.full((1, 12), 0.0)])
    rows[-1, 7] = 6.0
    lengths = explain.path_lengths(rows)
    score = 2 ** (-lengths / average_path_length(np.array([forest.max_samples_]))[0])
    assert np.allclose(score, -forest.score_samples(rows), atol=1e-12)
    parts = explain.parts(rows)
    assert np.allclose(parts.sum(axis=1), explain.base - lengths, atol=1e-9)
    # The one far-off feature is what isolated the last row.
    assert int(np.argmax(parts[-1])) == 7 and parts[-1, 7] > parts[-1].sum() / 2
