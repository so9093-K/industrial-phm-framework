"""Bounded selection context for an isolated bearing investigation walkthrough."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from industrial_phm.application.phm_analysis import (
    PhmAnalysisError,
    SqlitePhmAnalysisStore,
    StepState,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def read_bearing_journey(root: Path) -> dict[str, Any] | None:
    path = OperationsWorkspace(root).web_context_path
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        return None
    if raw.get("kind") != "bearing-demo" or raw.get("dataset") not in {"synthetic", "xjtu-sy"}:
        return None
    if any(
        not isinstance(raw.get(key), str) or not 1 <= len(raw[key]) <= 256
        for key in ("asset_id", "feature", "other_feature")
    ):
        return None
    bindings = raw.get("bindings")
    if (
        not isinstance(bindings, list)
        or len(bindings) != 2
        or any(not isinstance(value, str) or not 1 <= len(value) <= 256 for value in bindings)
    ):
        return None
    if any(type(raw.get(key)) is not int for key in ("first", "last")):
        return None
    if not 1 <= raw["first"] < raw["last"]:
        return None
    return {
        key: raw[key]
        for key in ("dataset", "asset_id", "bindings", "first", "last", "feature", "other_feature")
    }


def order_by_exceedance(root: Path, journey: dict[str, Any]) -> dict[str, Any]:
    """Put first the models whose latest analyzed measurement is over their own threshold.

    The guide opens the first model, so the walkthrough starts from the result a person
    would review. Scores are read as stored when asked; otherwise the order is unchanged.
    """
    path = OperationsWorkspace(root).phm_analysis_path
    if not path.is_file():
        return journey
    store = SqlitePhmAnalysisStore(path)
    try:
        latest = {
            binding: store.latest_result(binding, state=StepState.ANALYZED)
            for binding in journey["bindings"]
        }
    except OSError, sqlite3.Error, PhmAnalysisError:
        return journey
    over = [
        binding
        for binding, result in latest.items()
        if result is not None and result.output.get("exceeds_threshold") is True
    ]
    rest = [binding for binding in journey["bindings"] if binding not in over]
    return {**journey, "bindings": [*over, *rest]}
