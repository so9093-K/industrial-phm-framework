from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import industrial_phm.commands.operations as operations_commands
from industrial_phm.cli import main
from industrial_phm.runtime import (
    OperationsSupervisorStateKind,
    OperationsWorkspace,
    initialize_operations_workspace,
)


def test_operations_up_creates_fresh_workspace_and_starts_node(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "plant-new"
    captured = {}

    def fake_run(plan):
        captured["plan"] = plan
        return SimpleNamespace(
            state=SimpleNamespace(
                failure=None,
                state=OperationsSupervisorStateKind.STOPPED,
            ),
            exit_code=0,
        )

    monkeypatch.setattr(operations_commands, "run_operations_supervisor", fake_run)

    exit_code = main(["operations", "up", str(root)])

    assert exit_code == 0
    assert captured["plan"].workspace.root == root
    assert captured["plan"].ui_mode.value == "web-controlled"
    assert OperationsWorkspace(root).config_path.is_file()
    output = capsys.readouterr().out
    assert f"workspace={root} state=created" in output
    assert "operations_url=http://127.0.0.1:2718/web/" in output


def test_operations_up_reopens_initialized_workspace(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-existing")
    initialize_operations_workspace(workspace)
    capsys.readouterr()

    def fake_run(plan):
        assert plan.workspace == workspace
        return SimpleNamespace(
            state=SimpleNamespace(
                failure=None,
                state=OperationsSupervisorStateKind.STOPPED,
            ),
            exit_code=0,
        )

    monkeypatch.setattr(operations_commands, "run_operations_supervisor", fake_run)

    exit_code = main(["operations", "up", str(workspace.root)])

    assert exit_code == 0
    assert f"workspace={workspace.root} state=existing" in capsys.readouterr().out


def test_operations_up_adopts_recognized_pre_config_workspace_without_losing_state(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-legacy")
    workspace.root.mkdir()
    workspace.source_registry_path.write_text('{"sources": []}\n', encoding="utf-8")
    before = workspace.source_registry_path.read_bytes()

    def fake_run(plan):
        assert plan.workspace == workspace
        return SimpleNamespace(
            state=SimpleNamespace(
                failure=None,
                state=OperationsSupervisorStateKind.STOPPED,
            ),
            exit_code=0,
        )

    monkeypatch.setattr(operations_commands, "run_operations_supervisor", fake_run)

    exit_code = main(["operations", "up", str(workspace.root)])

    assert exit_code == 0
    assert workspace.config_path.is_file()
    assert workspace.source_registry_path.read_bytes() == before
    assert f"workspace={workspace.root} state=adopted-existing" in capsys.readouterr().out


def test_operations_up_refuses_unrecognized_directory_with_next_action(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    unrelated = root / "unrelated.txt"
    unrelated.write_text("keep", encoding="utf-8")

    exit_code = main(["operations", "up", str(root)])

    assert exit_code == 1
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not (root / "config.toml").exists()
    error = capsys.readouterr().err
    assert "Existing files were found" in error
    assert "were not changed" in error
    assert f"industrial-phm operations up {tmp_path / 'existing-new'}" in error


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
    assert plan.ui_mode.value == "web-controlled"
    assert tuple(component.kind.value for component in plan.components) == (
        "collection",
        "analysis",
        "ui",
    )
    output = capsys.readouterr().out
    assert f"workspace={workspace.root}" in output
    assert "operations_url=http://127.0.0.1:2718/web/" in output
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


def test_operations_stop_is_done_when_nothing_runs_and_clears_left_components(
    tmp_path: Path, capsys
) -> None:
    import subprocess
    import sys
    from datetime import UTC, datetime

    from industrial_phm.runtime.operations_runtime import OperationsComponentKind
    from industrial_phm.runtime.operations_supervisor import (
        OperationsChildProcessState,
        OperationsSupervisorState,
        OperationsSupervisorStateKind,
        OperationsSupervisorStateRepository,
    )

    workspace = OperationsWorkspace(tmp_path / "plant-a")
    other = OperationsWorkspace(tmp_path / "plant-b")
    for item in (workspace, other):
        initialize_operations_workspace(item)
        item.logs_path.mkdir(parents=True, exist_ok=True)
    assert main(["operations", "stop", str(workspace.root)]) == 0
    assert "stop=already-stopped last_state=none" in capsys.readouterr().out

    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    logs = []

    def spawn(log_root: OperationsWorkspace, kind: str, *role: str) -> subprocess.Popen:
        log = (log_root.logs_path / f"{kind}.log").open("ab")
        logs.append(log)
        return subprocess.Popen([*sleeper, *role], stdout=log, stderr=log)

    analysis_role = ("internal", "window-analysis", "--workspace")
    # Left by a vanished supervisor of plant-a: its analysis role, workspace and log.
    left = spawn(workspace, "analysis", *analysis_role, str(workspace.root))
    # Each misses one identity condition and must keep running.
    other_workspace = spawn(other, "analysis", *analysis_role, str(other.root))
    wrong_role = spawn(
        workspace, "collection", "internal", "window-analysis", "--workspace", str(workspace.root)
    )
    unrelated = subprocess.Popen(sleeper)
    at = datetime(2026, 10, 14, 1, 0, tzinfo=UTC)

    def recorded(kind: OperationsComponentKind, pid: int) -> OperationsChildProcessState:
        return OperationsChildProcessState(kind, pid, workspace.logs_path / f"{kind.value}.log")

    OperationsSupervisorStateRepository(workspace.supervisor_state_path).write(
        OperationsSupervisorState(
            state=OperationsSupervisorStateKind.RUNNING,
            supervisor_pid=unrelated.pid,
            started_at=at,
            updated_at=at,
            components=(
                recorded(OperationsComponentKind.COLLECTION, wrong_role.pid),
                recorded(OperationsComponentKind.ANALYSIS, left.pid),
                recorded(OperationsComponentKind.UI, other_workspace.pid),
            ),
        )
    )
    try:
        assert main(["operations", "stop", str(workspace.root)]) == 0
        out = capsys.readouterr().out
        assert "last_state=ended-without-stopping" in out
        assert f"leftover_stopped={left.pid}" in out
        assert left.wait(timeout=5) is not None
        assert all(p.poll() is None for p in (other_workspace, wrong_role, unrelated))
        state = OperationsSupervisorStateRepository(workspace.supervisor_state_path).load()
        assert state is not None and state.state == OperationsSupervisorStateKind.FAILED
        assert state.failure == "supervisor ended without stopping its components"
        assert main(["operations", "stop", str(workspace.root)]) == 0
        assert "last_state=failed" in capsys.readouterr().out
    finally:
        for log in logs:
            log.close()
        for process in (left, other_workspace, wrong_role, unrelated):
            process.kill()
            process.wait()


def test_operations_up_names_a_port_held_by_another_process(tmp_path: Path, capsys) -> None:
    import socket

    from industrial_phm.runtime.operations_config import (
        OperationsUiConfig,
        write_operations_runtime_config,
    )

    workspace = OperationsWorkspace(tmp_path / "plant-a")
    result = initialize_operations_workspace(workspace)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        write_operations_runtime_config(
            workspace.config_path, replace(result.config, ui=OperationsUiConfig(port=port))
        )
        assert main(["operations", "up", str(workspace.root)]) == 1
    error = capsys.readouterr().err
    assert f"127.0.0.1:{port} is used by another process" in error
    assert not workspace.supervisor_state_path.exists()
