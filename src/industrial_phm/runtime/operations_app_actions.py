"""Concrete write-side actions for the packaged Operations application.

The marimo app owns interaction state and form-to-domain input mapping. Concrete
repository construction, persistence refreshes, and diagnostic event-loop bridging
belong to the local runtime composition boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from industrial_phm.application import (
    CollectionControlRecord,
    CollectionDesiredState,
    FileSourceConfig,
    FindingReviewAction,
    FindingReviewEvent,
    JsonFileFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    OperationalAnalysisResult,
    OperationalFinding,
    RegisteredFileFeatureAnalysis,
    RegisteredOpcUaSubscriptionCycleResult,
    RegisteredSource,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceRuntimeCycleResult,
    create_finding_review_event,
    create_human_review_finding,
    register_file_source,
    request_collection_state,
    run_registered_file_feature_analysis,
    run_registered_file_source_cycle,
    run_registered_opcua_source_cycle,
    run_registered_opcua_subscription_cycle,
    transition_source_lifecycle,
    validate_distinct_source_state_paths,
)
from industrial_phm.connectors import (
    OpcUaBrowseConfig,
    OpcUaBrowseResult,
    browse_opcua_variables,
)
from industrial_phm.runtime.collection_control import SqliteCollectionControlRepository
from industrial_phm.runtime.operations_app_wiring import (
    OperationsAppPaths,
    OperationsSourceRegistryState,
    operations_source_registry_state,
    run_async_in_worker,
)


class OperationsDiagnosticKind(StrEnum):
    """Explicit bounded diagnostic modes exposed by Setup."""

    CYCLE = "cycle"
    SUBSCRIPTION = "subscription"


@dataclass(frozen=True, slots=True)
class OperationsAppActions:
    """Concrete local write/action facade for one resolved Operations workspace."""

    paths: OperationsAppPaths

    def set_freshness_policy(
        self,
        source_id: str,
        *,
        max_observation_age_seconds: float | None,
        changed_at: datetime,
    ) -> tuple[SourceFreshnessPolicy | None, OperationsSourceRegistryState]:
        repository = JsonSourceRepository(self.paths.registry)
        if max_observation_age_seconds is None:
            repository.clear_freshness_policy(source_id)
            policy = None
        else:
            policy = SourceFreshnessPolicy(
                source_id=source_id,
                max_observation_age_seconds=max_observation_age_seconds,
                changed_at=changed_at,
            )
            repository.set_freshness_policy(policy)
        return policy, operations_source_registry_state(repository)

    def browse_opcua(
        self,
        *,
        endpoint_url: str,
        timeout_seconds: float,
    ) -> OpcUaBrowseResult:
        """Run one bounded OPC UA browse without exposing event-loop plumbing to the UI."""
        config = OpcUaBrowseConfig(
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
        )
        return run_async_in_worker(lambda: browse_opcua_variables(config))

    def run_diagnostic(
        self,
        source_id: str,
        *,
        kind: OperationsDiagnosticKind,
    ) -> tuple[
        SourceRuntimeCycleResult | RegisteredOpcUaSubscriptionCycleResult,
        OperationsSourceRegistryState,
    ]:
        if not isinstance(kind, OperationsDiagnosticKind):
            raise ValueError("kind must be an OperationsDiagnosticKind")
        validate_distinct_source_state_paths(self.paths.registry, self.paths.source_runtime)
        source_repository = JsonSourceRepository(self.paths.registry)
        runtime_repository = JsonSourceRuntimeRepository(self.paths.source_runtime)
        source = source_repository.get(source_id)
        result: SourceRuntimeCycleResult | RegisteredOpcUaSubscriptionCycleResult

        if kind == OperationsDiagnosticKind.CYCLE:
            if isinstance(source.config, FileSourceConfig):
                result = run_registered_file_source_cycle(
                    source_repository,
                    source_repository,
                    runtime_repository,
                    source.source_id,
                )
            elif isinstance(source.config, OpcUaSourceConfig):
                result = run_async_in_worker(
                    lambda: run_registered_opcua_source_cycle(
                        source_repository,
                        source_repository,
                        runtime_repository,
                        source.source_id,
                    )
                )
            else:  # pragma: no cover - RegisteredSource validates supported config types.
                raise ValueError("unsupported registered source config")
        else:
            if not isinstance(source.config, OpcUaSourceConfig):
                raise ValueError("bounded subscription diagnostics require an OPC UA source")
            max_events = max(1, len(source.config.node_mappings))
            result = run_async_in_worker(
                lambda: run_registered_opcua_subscription_cycle(
                    source_repository,
                    source_repository,
                    runtime_repository,
                    source.source_id,
                    publishing_interval_ms=500.0,
                    collection_timeout_seconds=5.0,
                    max_events=max_events,
                    queue_maxsize=128,
                )
            )

        return result, operations_source_registry_state(source_repository)

    def transition_source(
        self,
        source_id: str,
        target: SourceLifecycleState,
        *,
        changed_at: datetime,
    ) -> tuple[SourceLifecycleRecord, OperationsSourceRegistryState]:
        repository = JsonSourceRepository(self.paths.registry)
        record = transition_source_lifecycle(
            repository,
            source_id,
            target,
            changed_at=changed_at,
        )
        return record, operations_source_registry_state(repository)

    def request_collection(
        self,
        source_id: str,
        target: CollectionDesiredState,
        *,
        requested_at: datetime,
    ) -> tuple[CollectionControlRecord, tuple[CollectionControlRecord, ...]]:
        source_repository = JsonSourceRepository(self.paths.registry)
        control_repository = SqliteCollectionControlRepository(self.paths.collection_control)
        record = request_collection_state(
            source_repository,
            source_repository,
            control_repository,
            source_id,
            target,
            requested_at=requested_at,
        )
        return record, control_repository.list_records()

    def register_source(
        self,
        source: RegisteredSource,
    ) -> OperationsSourceRegistryState:
        repository = JsonSourceRepository(self.paths.registry)
        if isinstance(source.config, FileSourceConfig):
            register_file_source(source, repository)
        elif isinstance(source.config, OpcUaSourceConfig):
            repository.register(source)
        else:  # pragma: no cover - RegisteredSource validates supported config types.
            raise ValueError("unsupported registered source config")
        return operations_source_registry_state(repository)

    def record_file_analysis(
        self,
        source: RegisteredSource,
    ) -> tuple[
        RegisteredFileFeatureAnalysis,
        tuple[RegisteredFileFeatureAnalysis, ...],
    ]:
        result = run_registered_file_feature_analysis(source)
        repository = JsonFileFeatureAnalysisRepository(self.paths.file_feature_analysis)
        repository.record(result)
        return result, repository.list_results()

    def request_review(
        self,
        result: OperationalAnalysisResult,
    ) -> tuple[OperationalFinding, tuple[OperationalFinding, ...]]:
        finding = create_human_review_finding(result)
        repository = JsonOperationalFindingRepository(self.paths.findings)
        repository.record(finding)
        return finding, repository.list_findings()

    def record_review_action(
        self,
        finding: OperationalFinding,
        *,
        action: FindingReviewAction,
        note: str,
    ) -> tuple[FindingReviewEvent, tuple[FindingReviewEvent, ...]]:
        event = create_finding_review_event(finding, action=action, note=note)
        repository = JsonFindingReviewRepository(self.paths.review)
        repository.record(event)
        return event, repository.list_events()
