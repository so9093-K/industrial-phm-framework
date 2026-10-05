"""Concrete read-side composition for the packaged Operations application.

The marimo app should render operator workflows, not know how every JSON/SQLite/
DuckLake repository is wired. Shared path wiring is resolved by operations_app_wiring;
this module owns one bounded, error-tolerant operational read snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from industrial_phm.application import (
    AcquisitionTelemetrySurface,
    CollectionControlRecord,
    CollectionServiceRuntimeTelemetry,
    FindingReviewEvent,
    JsonFileFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRuntimeRepository,
    JsonWindowAnalysisRuntimeRepository,
    LiveFlowTiming,
    OperationalAnalysisResult,
    OperationalFinding,
    OperationsMonitorView,
    OperationsOverview,
    PhaseUnbalanceAnalysis,
    RegisteredFileFeatureAnalysis,
    RegisteredSource,
    SourceConnectionAttemptEvidence,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceReceiptEvidence,
    SourceType,
    SqliteObservationWindowRepository,
    SqlitePhaseUnbalanceRepository,
    SqliteWindowAnalysisLedger,
    SystemStateErrorEvidence,
    WindowAnalysisRunnerTelemetry,
    WindowAnalysisState,
    build_operations_attention_queue,
    build_operations_monitor_view,
    build_operations_overview,
    collection_service_issue,
    validate_distinct_source_state_paths,
)
from industrial_phm.application.measurement_history import HistoryAssetSummary
from industrial_phm.application.operations_assets import AssetWorkspaceAnalysisAttempt
from industrial_phm.application.operations_monitor import (
    COLLECTION_SERVICE_TIMEOUT,
    LIVE_FLOW_SILENCE_TIMEOUT,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.acquisition_spool import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
)
from industrial_phm.runtime.acquisition_telemetry import (
    SqliteAcquisitionTelemetryRepository,
)
from industrial_phm.runtime.collection_control import SqliteCollectionControlRepository
from industrial_phm.runtime.operations_app_wiring import (
    OperationsAppPaths,
    load_operations_source_registry_state,
    resolve_operations_app_paths,
)
from industrial_phm.runtime.operations_live import (
    OperationsReadError,
    list_operations_history_assets,
)

_PHASE_RESULT_LIMIT = 500


@dataclass(frozen=True, slots=True)
class OperationsAppSnapshot:
    """Bounded operator-facing evidence loaded from concrete repositories."""

    paths: OperationsAppPaths
    assessed_at: datetime
    registered_sources: tuple[RegisteredSource, ...]
    lifecycle_records: tuple[SourceLifecycleRecord, ...]
    freshness_policies: tuple[SourceFreshnessPolicy, ...]
    analysis_results: tuple[OperationalAnalysisResult, ...]
    findings: tuple[OperationalFinding, ...]
    review_events: tuple[FindingReviewEvent, ...]
    acquisition_surfaces: tuple[AcquisitionTelemetrySurface, ...]
    collection_service: CollectionServiceRuntimeTelemetry | None
    analysis_runtime: WindowAnalysisRunnerTelemetry | None
    history_reader: DuckLakeAssetHistory | None
    history_assets: tuple[HistoryAssetSummary, ...]
    collection_records: tuple[CollectionControlRecord, ...]
    skipped_analysis_attempts: tuple[AssetWorkspaceAnalysisAttempt, ...]
    overview: OperationsOverview
    monitor: OperationsMonitorView
    live_flow_timing: LiveFlowTiming
    system_diagnostics: tuple[tuple[str, str], ...]
    system_errors: tuple[SystemStateErrorEvidence, ...]


def load_operations_app_snapshot(
    *,
    environ: Mapping[str, str] | None = None,
    assessed_at: datetime | None = None,
) -> OperationsAppSnapshot:
    """Load one bounded read snapshot without hiding repository-specific failures."""
    paths = resolve_operations_app_paths(environ)
    effective_at = datetime.now(UTC) if assessed_at is None else assessed_at
    if effective_at.utcoffset() is None:
        raise ValueError("assessed_at must be timezone-aware")

    system_errors: list[SystemStateErrorEvidence] = []
    registered_sources, lifecycle_records, freshness_policies = _load_sources(
        paths, effective_at, system_errors
    )
    receipts, connection_attempts = _load_source_runtime(
        paths, registered_sources, effective_at, system_errors
    )
    file_feature_results = _load_file_feature_results(paths, effective_at, system_errors)
    phase_results, phase_repository, phase_result_total = _load_phase_results(
        paths, effective_at, system_errors
    )
    skipped_analysis_attempts = _load_skipped_analysis_attempts(paths, effective_at, system_errors)
    findings = _load_findings(paths, effective_at, system_errors)
    phase_results = _include_review_referenced_phase_results(
        phase_results,
        phase_repository,
        findings,
        effective_at,
        system_errors,
    )
    phase_result_query_summary = (
        f"loaded {len(phase_results)} of {phase_result_total}; "
        f"newest up to {_PHASE_RESULT_LIMIT} plus review-referenced exact runs"
        if phase_repository is not None
        else "unavailable"
    )
    analysis_results: tuple[OperationalAnalysisResult, ...] = tuple(
        sorted(
            (*file_feature_results, *phase_results),
            key=lambda item: (item.run.completed_at, item.run.analysis_run_id),
        )
    )
    analysis_runs = tuple(item.run for item in analysis_results)
    review_events = _load_review_events(paths, effective_at, system_errors)

    overview = build_operations_overview(
        sources=registered_sources,
        lifecycle_records=lifecycle_records,
        receipts=receipts,
        freshness_policies=freshness_policies,
        connection_attempts=connection_attempts,
        analysis_runs=analysis_runs,
        findings=findings,
        review_events=review_events,
        as_of=effective_at,
    )
    acquisition_surfaces, collection_service = _load_acquisition(
        paths, registered_sources, effective_at, system_errors
    )
    analysis_runtime = _load_analysis_runtime(paths, effective_at, system_errors)
    history_reader, history_assets = _load_history(paths, effective_at, system_errors)
    collection_records = _load_collection_records(paths, effective_at, system_errors)

    attention = build_operations_attention_queue(
        overview=overview,
        system_errors=tuple(system_errors),
    )
    monitor = build_operations_monitor_view(
        sources=registered_sources,
        overview=overview,
        attention=attention,
        acquisition_surfaces=acquisition_surfaces,
        analysis_runs=analysis_runs,
        analysis_runtime=analysis_runtime,
        collection_service=collection_service,
        as_of=effective_at,
    )
    live_flow_timing = LiveFlowTiming(
        max_silence=LIVE_FLOW_SILENCE_TIMEOUT,
        as_of=effective_at,
        collection_service_down=collection_service_issue(
            collection_service,
            as_of=effective_at,
            timeout=COLLECTION_SERVICE_TIMEOUT,
            live_telemetry=bool(acquisition_surfaces),
        )
        is not None,
    )
    diagnostics = (
        ("Source registry", str(paths.registry)),
        ("Source runtime", str(paths.source_runtime)),
        ("Acquisition telemetry", str(paths.acquisition_telemetry)),
        ("Acquisition spool", str(paths.acquisition_spool)),
        ("Collection control", str(paths.collection_control)),
        ("Asset History catalog", str(paths.history_catalog)),
        ("Asset History data", str(paths.history_data)),
        ("Vibration analysis", str(paths.file_feature_analysis)),
        ("Three-phase analysis", str(paths.phase_analysis)),
        ("Three-phase result query", phase_result_query_summary),
        ("Analysis service runtime", str(paths.analysis_runtime)),
        ("Finalized windows", str(paths.window_state)),
        ("Analysis skip ledger", str(paths.analysis_ledger)),
        ("Review requests", str(paths.findings)),
        ("Maintenance review", str(paths.review)),
    )
    return OperationsAppSnapshot(
        paths=paths,
        assessed_at=effective_at,
        registered_sources=registered_sources,
        lifecycle_records=lifecycle_records,
        freshness_policies=freshness_policies,
        analysis_results=analysis_results,
        findings=findings,
        review_events=review_events,
        acquisition_surfaces=acquisition_surfaces,
        collection_service=collection_service,
        analysis_runtime=analysis_runtime,
        history_reader=history_reader,
        history_assets=history_assets,
        collection_records=collection_records,
        skipped_analysis_attempts=skipped_analysis_attempts,
        overview=overview,
        monitor=monitor,
        live_flow_timing=live_flow_timing,
        system_diagnostics=diagnostics,
        system_errors=tuple(system_errors),
    )


def _append_error(
    errors: list[SystemStateErrorEvidence],
    scope: str,
    error: object,
    assessed_at: datetime,
) -> None:
    errors.append(SystemStateErrorEvidence(scope, str(error), assessed_at))


def _load_sources(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[
    tuple[RegisteredSource, ...],
    tuple[SourceLifecycleRecord, ...],
    tuple[SourceFreshnessPolicy, ...],
]:
    try:
        state = load_operations_source_registry_state(paths.registry)
        return state.sources, state.lifecycles, state.freshness_policies
    except (OSError, ValueError) as error:
        _append_error(errors, "source-settings", error, assessed_at)
        return (), (), ()


def _load_source_runtime(
    paths: OperationsAppPaths,
    sources: tuple[RegisteredSource, ...],
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[
    tuple[SourceReceiptEvidence, ...],
    tuple[SourceConnectionAttemptEvidence, ...],
]:
    try:
        validate_distinct_source_state_paths(paths.registry, paths.source_runtime)
        repository = JsonSourceRuntimeRepository(paths.source_runtime)
        source_ids = {source.source_id for source in sources}
        receipts = tuple(
            item for item in repository.list_latest_receipts() if item.source_id in source_ids
        )
        attempts = tuple(
            item
            for item in repository.list_latest_connection_attempts()
            if item.source_id in source_ids
        )
        return receipts, attempts
    except (OSError, ValueError) as error:
        _append_error(errors, "source-runtime", error, assessed_at)
        return (), ()


def _load_file_feature_results(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[RegisteredFileFeatureAnalysis, ...]:
    try:
        return JsonFileFeatureAnalysisRepository(paths.file_feature_analysis).list_results()
    except (OSError, ValueError) as error:
        _append_error(errors, "file-feature-analysis-results", error, assessed_at)
        return ()


def _load_phase_results(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[
    tuple[PhaseUnbalanceAnalysis, ...],
    SqlitePhaseUnbalanceRepository | None,
    int,
]:
    try:
        repository = SqlitePhaseUnbalanceRepository(paths.phase_analysis)
        total = repository.count_results()
        return repository.list_recent_results(_PHASE_RESULT_LIMIT), repository, total
    except (OSError, ValueError) as error:
        _append_error(errors, "phase-analysis-results", error, assessed_at)
        return (), None, 0


def _load_skipped_analysis_attempts(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[AssetWorkspaceAnalysisAttempt, ...]:
    if not paths.window_state.is_file() or not paths.analysis_ledger.is_file():
        return ()
    try:
        windows = SqliteObservationWindowRepository(paths.window_state)
        ledger = SqliteWindowAnalysisLedger(paths.analysis_ledger)
        attempts: list[AssetWorkspaceAnalysisAttempt] = []
        unresolved: list[str] = []
        for outcome in ledger.list_skipped():
            if outcome.reason is None:
                raise ValueError(f"skipped window {outcome.window_id} has no recorded reason")
            try:
                window = windows.get(outcome.window_id)
            except KeyError:
                unresolved.append(outcome.window_id)
                continue
            attempts.append(
                AssetWorkspaceAnalysisAttempt(
                    asset_id=window.asset_id,
                    state=WindowAnalysisState.SKIPPED,
                    capability_id=outcome.capability_id,
                    source_id=window.source_id,
                    measurement_point_id=window.measurement_point_id,
                    observed_start_at=window.window_start,
                    observed_end_at=window.window_end,
                    recorded_at=outcome.recorded_at,
                    window_id=window.window_id,
                    reason=outcome.reason,
                )
            )
        if unresolved:
            errors.append(
                SystemStateErrorEvidence(
                    "analysis-attempts",
                    (
                        f"{len(unresolved)} skipped analysis attempt(s) reference windows "
                        "that are no longer stored; their asset and range are unavailable"
                    ),
                    assessed_at,
                )
            )
        return tuple(
            sorted(
                attempts,
                key=lambda item: (-item.recorded_at.timestamp(), item.window_id or ""),
            )
        )
    except (KeyError, LookupError, OSError, ValueError) as error:
        _append_error(errors, "analysis-attempts", error, assessed_at)
        return ()


def _load_findings(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[OperationalFinding, ...]:
    try:
        return JsonOperationalFindingRepository(paths.findings).list_findings()
    except (OSError, ValueError) as error:
        _append_error(errors, "review-requests", error, assessed_at)
        return ()


def _include_review_referenced_phase_results(
    phase_results: tuple[PhaseUnbalanceAnalysis, ...],
    repository: SqlitePhaseUnbalanceRepository | None,
    findings: tuple[OperationalFinding, ...],
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[PhaseUnbalanceAnalysis, ...]:
    if repository is None:
        return phase_results
    loaded_run_ids = {item.run.analysis_run_id for item in phase_results}
    reviewed_run_ids = {finding.analysis_run_id for finding in findings}
    try:
        reviewed = repository.find_results(reviewed_run_ids - loaded_run_ids)
    except (OSError, ValueError) as error:
        _append_error(errors, "phase-analysis-review-results", error, assessed_at)
        return phase_results
    if not reviewed:
        return phase_results
    return tuple(
        sorted(
            (*phase_results, *reviewed),
            key=lambda item: (item.run.completed_at, item.run.analysis_run_id),
        )
    )


def _load_review_events(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[FindingReviewEvent, ...]:
    try:
        return JsonFindingReviewRepository(paths.review).list_events()
    except (OSError, ValueError) as error:
        _append_error(errors, "maintenance-review", error, assessed_at)
        return ()


def _load_acquisition(
    paths: OperationsAppPaths,
    sources: tuple[RegisteredSource, ...],
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[
    tuple[AcquisitionTelemetrySurface, ...],
    CollectionServiceRuntimeTelemetry | None,
]:
    if not paths.acquisition_telemetry.is_file() or not paths.acquisition_spool.is_file():
        return (), None
    surfaces: list[AcquisitionTelemetrySurface] = []
    try:
        telemetry = SqliteAcquisitionTelemetryRepository(paths.acquisition_telemetry)
        service = telemetry.get_collection_service_runtime()
        spool = SqliteAcquisitionSpool(
            SqliteAcquisitionSpoolConfig(path=paths.acquisition_spool)
        ).telemetry_snapshot(sampled_at=assessed_at)
        for source in sources:
            if source.source_type != SourceType.OPCUA:
                continue
            try:
                surfaces.append(
                    AcquisitionTelemetrySurface(
                        source=telemetry.get(source.source_id),
                        spool=spool,
                    )
                )
            except (LookupError, OSError, ValueError) as error:
                _append_error(errors, f"live-data:{source.source_id}", error, assessed_at)
        return tuple(surfaces), service
    except (OSError, ValueError) as error:
        _append_error(errors, "live-data", error, assessed_at)
        return tuple(surfaces), None


def _load_analysis_runtime(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> WindowAnalysisRunnerTelemetry | None:
    if not paths.analysis_runtime.is_file():
        return None
    try:
        return JsonWindowAnalysisRuntimeRepository(paths.analysis_runtime).load()
    except (OSError, ValueError) as error:
        _append_error(errors, "analysis-service", error, assessed_at)
        return None


def _load_history(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[DuckLakeAssetHistory | None, tuple[HistoryAssetSummary, ...]]:
    if not paths.history_catalog.is_file():
        return None, ()
    try:
        reader = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(paths.history_catalog, paths.history_data)
        )
        return reader, list_operations_history_assets(reader)
    except OperationsReadError as error:
        _append_error(errors, "asset-history", error, assessed_at)
        return None, ()


def _load_collection_records(
    paths: OperationsAppPaths,
    assessed_at: datetime,
    errors: list[SystemStateErrorEvidence],
) -> tuple[CollectionControlRecord, ...]:
    if not paths.collection_control.is_file():
        return ()
    try:
        return SqliteCollectionControlRepository(paths.collection_control).list_records()
    except (OSError, ValueError) as error:
        _append_error(errors, "collection-control", error, assessed_at)
        return ()
