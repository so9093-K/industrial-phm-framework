"""Shared concrete wiring primitives for the packaged Operations application."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from industrial_phm.application import (
    JsonSourceRepository,
    RegisteredSource,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


@dataclass(frozen=True, slots=True)
class OperationsAppPaths:
    """Resolved persistent paths used by one Operations app runtime."""

    workspace: OperationsWorkspace | None
    registry: Path
    source_runtime: Path
    acquisition_telemetry: Path
    acquisition_spool: Path
    collection_control: Path
    field_analysis: Path
    phase_analysis: Path
    analysis_runtime: Path
    window_state: Path
    analysis_ledger: Path
    findings: Path
    review: Path
    history_catalog: Path
    history_data: Path
    phase_analysis_explicit: bool


@dataclass(frozen=True, slots=True)
class OperationsSourceRegistryState:
    """Post-read/write source registry state shared by snapshot and actions."""

    sources: tuple[RegisteredSource, ...]
    lifecycles: tuple[SourceLifecycleRecord, ...]
    freshness_policies: tuple[SourceFreshnessPolicy, ...]


def resolve_operations_app_paths(
    environ: Mapping[str, str] | None = None,
) -> OperationsAppPaths:
    """Resolve one workspace-first path set with legacy explicit-path compatibility."""
    values = os.environ if environ is None else environ
    workspace_root = values.get("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE")
    workspace = None if workspace_root is None else OperationsWorkspace(Path(workspace_root))

    def runtime_path(
        env_name: str,
        workspace_path: Path | None,
        legacy_default: str | Path,
    ) -> Path:
        default = Path(legacy_default) if workspace is None else workspace_path
        if default is None:
            raise AssertionError(f"workspace path is required for {env_name}")
        return Path(values.get(env_name, str(default)))

    phase_analysis = runtime_path(
        "INDUSTRIAL_PHM_OPERATIONS_PHASE_UNBALANCE_STATE",
        None if workspace is None else workspace.phase_unbalance_state_path,
        "artifacts/operations/phase-unbalance.sqlite",
    )
    return OperationsAppPaths(
        workspace=workspace,
        registry=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY",
            None if workspace is None else workspace.source_registry_path,
            "artifacts/operations/source-registry.json",
        ),
        source_runtime=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_SOURCE_RUNTIME",
            None if workspace is None else workspace.source_runtime_path,
            "artifacts/operations/source-runtime.json",
        ),
        acquisition_telemetry=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_TELEMETRY",
            None if workspace is None else workspace.acquisition_telemetry_path,
            "artifacts/operations/acquisition-telemetry.sqlite",
        ),
        acquisition_spool=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_SPOOL",
            None if workspace is None else workspace.acquisition_spool_path,
            "artifacts/operations/acquisition-spool.sqlite",
        ),
        collection_control=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_COLLECTION_CONTROL",
            None if workspace is None else workspace.collection_control_path,
            "artifacts/operations/collection-control.sqlite",
        ),
        field_analysis=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_STATE",
            None if workspace is None else workspace.field_analysis_path,
            "artifacts/operations/field-analysis.json",
        ),
        phase_analysis=phase_analysis,
        analysis_runtime=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_RUNTIME",
            None if workspace is None else workspace.analysis_runtime_path,
            phase_analysis.with_name(f"{phase_analysis.stem}-runtime.json"),
        ),
        window_state=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_WINDOW_STATE",
            None if workspace is None else workspace.window_state_path,
            phase_analysis.with_name("windows.sqlite"),
        ),
        analysis_ledger=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_LEDGER",
            None if workspace is None else workspace.analysis_ledger_path,
            phase_analysis.with_name("window-analysis-ledger.sqlite"),
        ),
        findings=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_FINDING_STATE",
            None if workspace is None else workspace.finding_state_path,
            "artifacts/operations/findings.json",
        ),
        review=runtime_path(
            "INDUSTRIAL_PHM_OPERATIONS_MAINTENANCE_REVIEW_STATE",
            None if workspace is None else workspace.maintenance_review_state_path,
            "artifacts/operations/finding-review.json",
        ),
        history_catalog=runtime_path(
            "INDUSTRIAL_PHM_HISTORY_CATALOG",
            None if workspace is None else workspace.history_catalog_path,
            "artifacts/operations/history/catalog.sqlite",
        ),
        history_data=runtime_path(
            "INDUSTRIAL_PHM_HISTORY_DATA",
            None if workspace is None else workspace.history_data_path,
            "artifacts/operations/history/data",
        ),
        phase_analysis_explicit=("INDUSTRIAL_PHM_OPERATIONS_PHASE_UNBALANCE_STATE" in values),
    )


def load_operations_source_registry_state(
    path: Path,
) -> OperationsSourceRegistryState:
    """Load one complete source registry projection from its concrete local repository."""
    return operations_source_registry_state(JsonSourceRepository(path))


def operations_source_registry_state(
    repository: JsonSourceRepository,
) -> OperationsSourceRegistryState:
    """Project source/lifecycle/freshness state from one already-open repository."""
    sources = repository.list_sources()
    lifecycles = tuple(repository.get_lifecycle(source.source_id) for source in sources)
    freshness = tuple(
        policy
        for source in sources
        if (policy := repository.get_freshness_policy(source.source_id)) is not None
    )
    return OperationsSourceRegistryState(
        sources=sources,
        lifecycles=lifecycles,
        freshness_policies=freshness,
    )


def run_async_in_worker[T](
    factory: Callable[[], Coroutine[Any, Any, T]],
) -> T:
    """Execute one bounded async connector action outside a marimo event loop."""

    def run() -> T:
        return asyncio.run(factory())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run).result()
