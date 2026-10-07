from datetime import UTC, datetime

from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.operations_system import (
    SystemRuntimeFact,
    SystemRuntimeKind,
    SystemRuntimeService,
    SystemRuntimeView,
)
from industrial_phm.presentation.operations_system import (
    render_system_diagnostics_html,
    render_system_errors_html,
    render_system_runtime_html,
    system_workspace_css,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _view() -> SystemRuntimeView:
    services = tuple(
        SystemRuntimeService(
            kind=kind,
            title=kind.value.title(),
            status=OperationsMonitorStatus.RUNNING,
            summary=f"{kind.value} current",
            updated_at=NOW,
            facts=(SystemRuntimeFact("Last update", NOW.isoformat()),),
        )
        for kind in SystemRuntimeKind
    )
    return SystemRuntimeView(
        assessed_at=NOW,
        services=services,
        errors=(),
    )


def test_system_primary_surface_uses_runtime_facts_without_paths() -> None:
    rendered = render_system_runtime_html(_view())

    assert "Runtime" in rendered
    assert "Running" in rendered
    assert "Last update" in rendered
    assert "catalog.sqlite" not in rendered
    assert "source-runtime.json" not in rendered


def test_system_errors_empty_state_is_quiet() -> None:
    rendered = render_system_errors_html(_view())

    assert "No current state-read error is recorded." in rendered


def test_paths_are_only_rendered_by_advanced_diagnostics() -> None:
    rendered = render_system_diagnostics_html(
        (
            ("History catalog", "artifacts/operations/history/catalog.sqlite"),
            ("Source runtime", "artifacts/operations/source-runtime.json"),
        )
    )

    assert "Advanced diagnostics" in rendered
    assert "catalog.sqlite" in rendered
    assert "source-runtime.json" in rendered
    assert "var(--phm-border)" in system_workspace_css()


def test_system_runtime_locale_does_not_relabel_process_running_as_receiving() -> None:
    rendered = render_system_runtime_html(_view(), "ko-KR")

    assert "실행 중" in rendered
    assert "수신 중" not in rendered
