from pathlib import Path
from types import SimpleNamespace

import industrial_phm.commands.operations as operations_commands
from industrial_phm.cli import main
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace


def test_operations_start_runs_supervisor_from_workspace_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    captured = {}

    def fake_run(plan):
        captured["plan"] = plan
        return SimpleNamespace(
            state=SimpleNamespace(failure=None),
            exit_code=0,
        )

    monkeypatch.setattr(operations_commands, "run_operations_supervisor", fake_run)

    exit_code = main(["operations", "start", str(workspace.root)])

    assert exit_code == 0
    plan = captured["plan"]
    assert plan.workspace == workspace
    assert tuple(component.kind.value for component in plan.components) == (
        "collection",
        "analysis",
    )


def test_operations_start_requires_initialized_workspace(tmp_path: Path, capsys) -> None:
    root = tmp_path / "missing"

    exit_code = main(["operations", "start", str(root)])

    assert exit_code == 1
    assert "Operations runtime start failed" in capsys.readouterr().err


def test_operations_stop_requests_supervisor_shutdown(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    captured = {}

    def fake_stop(value: OperationsWorkspace) -> int:
        captured["workspace"] = value
        return 701

    monkeypatch.setattr(operations_commands, "request_operations_supervisor_stop", fake_stop)

    exit_code = main(["operations", "stop", str(workspace.root)])

    assert exit_code == 0
    assert captured["workspace"] == workspace
    assert "stop=requested supervisor_pid=701" in capsys.readouterr().out
