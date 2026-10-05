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
    """Compatibility projection over the authoritative Operations workspace layout."""

    workspace: OperationsWorkspace

    @property
    def registry(self) -> Path:
        return self.workspace.source_registry_path

    @property
    def source_runtime(self) -> Path:
        return self.workspace.source_runtime_path

    @property
    def acquisition_telemetry(self) -> Path:
        return self.workspace.acquisition_telemetry_path

    @property
    def acquisition_spool(self) -> Path:
        return self.workspace.acquisition_spool_path

    @property
    def collection_control(self) -> Path:
        return self.workspace.collection_control_path

    @property
    def file_feature_analysis(self) -> Path:
        return self.workspace.file_feature_analysis_path

    @property
    def phase_analysis(self) -> Path:
        return self.workspace.phase_unbalance_state_path

    @property
    def analysis_runtime(self) -> Path:
        return self.workspace.analysis_runtime_path

    @property
    def window_state(self) -> Path:
        return self.workspace.window_state_path

    @property
    def analysis_ledger(self) -> Path:
        return self.workspace.analysis_ledger_path

    @property
    def findings(self) -> Path:
        return self.workspace.finding_state_path

    @property
    def review(self) -> Path:
        return self.workspace.maintenance_review_state_path

    @property
    def history_catalog(self) -> Path:
        return self.workspace.history_catalog_path

    @property
    def history_data(self) -> Path:
        return self.workspace.history_data_path


@dataclass(frozen=True, slots=True)
class OperationsSourceRegistryState:
    """Post-read/write source registry state shared by snapshot and actions."""

    sources: tuple[RegisteredSource, ...]
    lifecycles: tuple[SourceLifecycleRecord, ...]
    freshness_policies: tuple[SourceFreshnessPolicy, ...]


def resolve_operations_app_paths(
    environ: Mapping[str, str] | None = None,
) -> OperationsAppPaths:
    """Resolve packaged Operations paths from one authoritative workspace root."""
    values = os.environ if environ is None else environ
    workspace_root = values.get("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE")
    if not workspace_root:
        raise ValueError(
            "INDUSTRIAL_PHM_OPERATIONS_WORKSPACE is required for the packaged Operations app"
        )
    workspace = OperationsWorkspace(Path(workspace_root))

    return OperationsAppPaths(workspace=workspace)


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
