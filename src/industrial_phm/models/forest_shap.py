"""Exact per-feature parts of an Isolation Forest score (path-dependent TreeSHAP).

An isolation tree scores a row by how few splits isolate it. Path-dependent TreeSHAP
(Lundberg et al., 2020) divides each tree's path length into one part per feature, so the
parts add up to the row's path length minus the tree's expected path length over its own
training sample. A leaf is a product game over the features on its path: a feature known to
the game follows the row (1 if the row takes that branch, else 0), an unknown one takes the
branch's share of the training sample. A player's Shapley value in such a game is the integral
over [0, 1] of a polynomial whose degree is below the path depth, so a few Gauss-Legendre
nodes give it exactly, for every leaf at once.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def average_path_length(samples: np.ndarray) -> np.ndarray:
    """Average path length of an unsuccessful search among ``samples`` points, c(n)."""
    n = np.asarray(samples, dtype=np.float64)
    out = np.zeros_like(n)
    out[n == 2] = 1.0
    many = n > 2
    out[many] = 2.0 * (np.log(n[many] - 1.0) + np.euler_gamma) - 2.0 * (n[many] - 1.0) / n[many]
    return out


class ForestShap:
    """Each feature's part in raising a fitted ``IsolationForest``'s anomaly score.

    A part is the average over trees of how much that feature shortened the row's path, so a
    positive part raised the score and the parts add up to the forest's expected path length
    minus the row's. Rows are compared as the forest compares them, in float32.
    """

    def __init__(self, forest: Any, width: int) -> None:
        paths: list[tuple[list[tuple[int, float, bool, float]], float]] = []
        base = 0.0
        for tree, features in zip(forest.estimators_, forest.estimators_features_, strict=True):
            nodes = tree.tree_
            counts = nodes.n_node_samples
            leaf_length = average_path_length(counts)
            stack: list[tuple[int, list[tuple[int, float, bool, float]]]] = [(0, [])]
            while stack:
                node, path = stack.pop()
                left, right = int(nodes.children_left[node]), int(nodes.children_right[node])
                if left == -1:
                    value = len(path) + float(leaf_length[node])
                    paths.append((path, value))
                    base += counts[node] / counts[0] * value
                    continue
                feature = int(features[int(nodes.feature[node])])
                threshold = float(nodes.threshold[node])
                for child, goes_left in ((left, True), (right, False)):
                    share = counts[child] / counts[node]
                    stack.append((child, [*path, (feature, threshold, goes_left, share)]))
        trees = len(forest.estimators_)
        depth = max(1, max(len(path) for path, _ in paths))
        leaves = len(paths)
        self.width = width
        self.base = base / trees
        self._trees = trees
        self._depth = depth
        self._feature = np.zeros((leaves, depth), dtype=np.int64)
        self._threshold = np.zeros((leaves, depth), dtype=np.float64)
        self._left = np.ones((leaves, depth), dtype=bool)
        self._used = np.zeros((leaves, depth), dtype=bool)
        # 한 경로에서 여러 번 갈라진 특징은 한 참가자다. 빈 자리는 버림 칸(depth)으로 보낸다.
        self._slot = np.full((leaves, depth), depth, dtype=np.int64)
        self._slot_feature = np.full((leaves, depth), width, dtype=np.int64)
        self._zero = np.ones((leaves, depth), dtype=np.float64)
        self._value = np.empty(leaves, dtype=np.float64)
        for leaf, (path, value) in enumerate(paths):
            self._value[leaf] = value
            slots: dict[int, int] = {}
            for step, (feature, threshold, goes_left, share) in enumerate(path):
                slot = slots.setdefault(feature, len(slots))
                self._feature[leaf, step] = feature
                self._threshold[leaf, step] = threshold
                self._left[leaf, step] = goes_left
                self._used[leaf, step] = True
                self._slot[leaf, step] = slot
                self._slot_feature[leaf, slot] = feature
                self._zero[leaf, slot] *= share
        # 적분할 다항식의 차수는 depth - 1 이하이므로 ceil(depth / 2)개 노드로 정확하다.
        nodes_, weights = np.polynomial.legendre.leggauss((depth + 1) // 2)
        self._nodes = (nodes_ + 1.0) / 2.0
        self._weights = weights / 2.0

    def path_lengths(self, rows: np.ndarray) -> np.ndarray:
        """The forest's average path length for each row (what its score is computed from)."""
        return np.asarray([self._value @ self._reaches(row).all(axis=1) for row in rows]) / (
            self._trees
        )

    def parts(self, rows: np.ndarray) -> np.ndarray:
        """Each row's per-feature parts; positive parts raised the anomaly score."""
        out = np.empty((len(rows), self.width), dtype=np.float64)
        leaves = np.arange(len(self._value))
        for index, row in enumerate(rows):
            reaches = self._reaches(row)
            one = np.ones((len(leaves), self._depth + 1), dtype=np.float64)
            for step in range(self._depth):
                one[leaves, self._slot[:, step]] *= reaches[:, step]
            one = one[:, : self._depth]
            gap = one - self._zero
            factors = self._zero[:, :, None] + gap[:, :, None] * self._nodes
            # 노드가 (0, 1) 안에 있고 분기 비율이 0보다 커서 각 인수는 0이 아니다.
            others = factors.prod(axis=1)[:, None, :] / factors
            shapley = self._value[:, None] * gap * (others @ self._weights)
            lengths = np.bincount(
                self._slot_feature.ravel(), weights=shapley.ravel(), minlength=self.width + 1
            )
            out[index] = -lengths[: self.width] / self._trees
        return out

    def _reaches(self, row: np.ndarray) -> np.ndarray:
        values = np.asarray(row, dtype=np.float32).astype(np.float64)[self._feature]
        below = values <= self._threshold
        return np.where(self._left, below, ~below) | ~self._used
