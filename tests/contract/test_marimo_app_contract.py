"""Structural regressions for repository marimo applications."""

import ast
from pathlib import Path

import pytest

from industrial_phm.apps import operations_app_path

REPO = Path(__file__).resolve().parents[2]
APPS = [*sorted((REPO / "apps").glob("*.py")), operations_app_path()]


def _ui_values_read_in_creating_cell(path: Path) -> list[str]:
    """Find UI elements whose value is read in the same cell that creates them."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for cell in tree.body:
        if not isinstance(cell, ast.FunctionDef):
            continue
        created = {
            target.id
            for node in ast.walk(cell)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func).startswith("mo.ui.")
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        callbacks = {
            id(inner)
            for node in ast.walk(cell)
            if isinstance(node, ast.Lambda)
            for inner in ast.walk(node)
        }
        problems += [
            f"{path.name}:{node.lineno} {node.value.id}.value"
            for node in ast.walk(cell)
            if isinstance(node, ast.Attribute)
            and node.attr == "value"
            and isinstance(node.value, ast.Name)
            and node.value.id in created
            and id(node) not in callbacks
        ]
    return problems


@pytest.mark.parametrize("path", APPS, ids=lambda path: path.name)
def test_no_cell_reads_the_value_of_a_ui_element_it_creates(path: Path) -> None:
    # marimo 0.24.2 raises this at runtime; its strict linter does not statically own it.
    assert _ui_values_read_in_creating_cell(path) == []
