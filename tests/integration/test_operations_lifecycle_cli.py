from pathlib import Path
from types import SimpleNamespace

import industrial_phm.commands.operations as operations_commands
from industrial_phm.cli import main
from industrial_phm.runtime import (
    OperationsSupervisorStateKind,
    OperationsWorkspace,
    initialize_operations_workspace,
)


def test_operations_start_runs_full_local_node_from_workspace_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    captured = {}

    def fake_run(plan):
        captured["plan"] = plan
        return SimpleNamespace(
            state=SimpleNamespace(
                failure=None,
                state=OperationsSupervisorStateKind.STOPPED,
            ),
            exit_code=130,
        )

    monkeypatch.setattr(operations_commands, "run_operations_supervisor", fake_run)

    exit_code = main(["operations", "start", str(workspace.root)])

    assert exit_code == 0
    plan = captured["plan"]
    assert plan.workspace == workspace
    assert tuple(component.kind.value for component in plan.components) == (
        "collection",
        "analysis",
        "ui",
    )
    output = capsys.readouterr().out
    assert f"workspace={workspace.root}" in output
    assert "operations_url=http://127.0.0.1:2718" in output
    assert "mode=foreground" in output


def test_operations_start_requires_initialized_workspace(tmp_path: Path, capsys) -> None:
    root = tmp_path / "missing"

    exit_code = main(["operations", "start", str(root)])

    assert exit_code == 1
    assert "Operations runtime start failed" in capsys.readouterr().err


def test_operations_logs_reads_bounded_component_tail(tmp_path: Path, capsys) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    workspace.logs_path.joinpath("ui.log").write_text(
        "line-1\nline-2\nline-3\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "operations",
            "logs",
            str(workspace.root),
            "--component",
            "ui",
            "--lines",
            "2",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "== ui ==" in output
    assert "line-1" not in output
    assert "line-2" in output
    assert "line-3" in output


def test_operations_logs_reports_no_written_logs_without_exposing_paths(
    tmp_path: Path,
    capsys,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)

    exit_code = main(["operations", "logs", str(workspace.root)])

    assert exit_code == 2
    output = capsys.readouterr().out
    assert output.count("[log unavailable: component has not written a log yet]") == 3
    assert str(workspace.logs_path) not in output


def test_operations_logs_rejects_unbounded_line_count(tmp_path: Path, capsys) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)

    exit_code = main(["operations", "logs", str(workspace.root), "--lines", "10001"])

    assert exit_code == 1
    assert "--lines must be between 1 and 10000" in capsys.readouterr().err


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
