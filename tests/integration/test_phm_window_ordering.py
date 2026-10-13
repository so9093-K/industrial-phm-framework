"""Late or out-of-order OPC UA events never leave a finalized window outside PHM results.

The PHM window runner reads windows after its cursor. That is only safe if the coordinator can
never persist, for one stream, a window that ends before a window it already persisted. This
drives the real incremental coordinator with shuffled event times, lateness allowances, small
history pages and coordinator restarts, running the PHM runner after every cycle.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    InMemorySourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SqliteObservationWindowRepository,
)
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_FEATURE_NAMES,
    ELECTRICAL_WINDOW_FEATURE_SET_ID,
)
from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaPersistentDataChangeEvent,
)
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
from industrial_phm.application.phm_runner import PackageCache, run_window_bindings
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent
from industrial_phm.application.window_coordinator import ObservationWindowCoordinatorPolicy
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    write_model_package,
)
from industrial_phm.runtime.window_coordinator import IncrementalRegisteredOpcUaWindowCoordinator

BASE = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
WIDTH = len(ELECTRICAL_WINDOW_FEATURE_NAMES)


class _History:
    """Durable history ordered by ingestion, as the DuckLake reader returns it."""

    def __init__(self) -> None:
        self.events: list[OpcUaPersistentDataChangeEvent] = []

    def query_opcua_events_after(self, source_id, *, cursor, limit):  # type: ignore[no-untyped-def]
        values = [e for e in self.events if e.source_id == source_id]
        if cursor is not None:
            key = (cursor.ingested_at, cursor.connection_epoch, cursor.event_index)
            values = [
                e
                for e in values
                if (e.event_time.ingested_at, e.connection_epoch, e.event_index) > key
            ]
        return tuple(values[:limit])

    def query_opcua_events_from_event_time(self, source_id, *, start_at):  # type: ignore[no-untyped-def]
        return tuple(
            e
            for e in self.events
            if e.source_id == source_id
            and (start_at is None or (e.event_time.event_at or start_at) >= start_at)
        )


def _event(index: int, event_at: datetime, ingested_at: datetime) -> OpcUaPersistentDataChangeEvent:
    observation = OpcUaNodeObservation(
        channel_id="voltage",
        node_id="ns=2;s=voltage",
        value=220.0 + index,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=event_at,
        received_at=ingested_at,
    )
    return OpcUaPersistentDataChangeEvent(
        event=RegisteredOpcUaDataChangeEvent(
            source_id="source-a",
            asset_id="asset-a",
            endpoint_url="opc.tcp://127.0.0.1:4840",
            collection_index=index,
            notification=OpcUaSubscriptionNotification(observation),
        ),
        connection_epoch=1,
        event_index=index,
        event_time=OpcUaEventTimeEvidence(
            basis=OpcUaEventTimeBasis.SOURCE_TIMESTAMP,
            source_timestamp=event_at,
            server_timestamp=event_at,
            received_at=ingested_at,
            ingested_at=ingested_at,
            event_at=event_at,
        ),
    )


def _package(models: Path) -> str:
    return write_model_package(
        models,
        PackageBuild(
            recipe_id="ordering-pca-v1",
            estimator_kind=EstimatorKind.PCA_RESIDUAL,
            input=PackageInputSpec(
                step_kind=StepKind.OBSERVATION_WINDOW,
                channels=("phase current R/S/T [A]", "phase voltage R/S/T [V]", "frequency [Hz]"),
                feature_set_id=ELECTRICAL_WINDOW_FEATURE_SET_ID,
                feature_names=ELECTRICAL_WINDOW_FEATURE_NAMES,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="spe",
                threshold=1.0,
                threshold_rule="fixed-for-test",
                review_interval=ReviewIntervalRule(2, 1),
                provides_feature_contributions=True,
            ),
            preprocessing=AffinePreprocessing((0.0,) * WIDTH, (1.0,) * WIDTH),
            estimator_state={"mean": [0.0] * WIDTH, "components": [[1.0] + [0.0] * (WIDTH - 1)]},
            fit_rows=None,
            probe_rows=[[1.0] * WIDTH],
            training_scope={},
            validation={},
            applicability={},
            created_at=BASE.isoformat(),
            code_revision="0" * 40,
        ),
    ).package_id


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("lateness", [0, 30, 90])
def test_out_of_order_events_never_finalize_an_older_window_after_a_newer_one(
    tmp_path: Path, seed: int, lateness: int
) -> None:
    rng = random.Random(seed * 1000 + lateness)
    sources = InMemorySourceRepository()
    sources.register(
        RegisteredSource(
            source_id="source-a",
            name="Line A",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="asset-a",
                node_mappings=(OpcUaNodeMapping("voltage", "ns=2;s=voltage"),),
            ),
            registered_at=BASE,
        )
    )
    history = _History()
    windows = SqliteObservationWindowRepository(tmp_path / "windows.sqlite")
    policy = ObservationWindowCoordinatorPolicy(
        window_duration_seconds=60,
        allowed_lateness_seconds=lateness,
        history_page_size=rng.choice([1, 3, 7]),
    )
    store = SqlitePhmAnalysisStore(tmp_path / "phm.sqlite")
    package_id = _package(tmp_path / "models")
    store.create_binding(
        PhmBinding("w", package_id, "source-a", "asset-a", StepKind.OBSERVATION_WINDOW, BASE)
    )

    # Event times jitter up to 150 s behind their ingestion, so arrivals are out of order and
    # some are later than the allowed lateness.
    ingested = BASE
    persisted_order: list[tuple[datetime, str]] = []
    coordinator = None
    for index in range(160):
        ingested += timedelta(seconds=rng.randint(1, 12))
        history.events.append(
            _event(index, ingested - timedelta(seconds=rng.randint(0, 150)), ingested)
        )
        if index % rng.randint(3, 9) == 0:
            if coordinator is None or rng.random() < 0.3:  # restart from durable state
                coordinator = IncrementalRegisteredOpcUaWindowCoordinator(
                    sources, history, windows, "source-a", policy=policy
                )
            before = {w.window_id for w in windows.list_windows()}
            for _ in range(5):
                coordinator.run_cycle()
            new = sorted(
                (w.window_end, w.window_id)
                for w in windows.list_windows()
                if w.window_id not in before
            )
            if persisted_order and new:
                assert new[0][0] > persisted_order[-1][0], "an older window was finalized late"
            persisted_order.extend(new)
            run_window_bindings(store, windows, PackageCache(tmp_path / "models"), now=lambda: BASE)

    for _ in range(5):
        IncrementalRegisteredOpcUaWindowCoordinator(
            sources, history, windows, "source-a", policy=policy
        ).run_cycle()
    run_window_bindings(store, windows, PackageCache(tmp_path / "models"), now=lambda: BASE)
    finalized = {w.window_id for w in windows.list_windows()}
    recorded = {r.input_reference["window_id"] for r in store.list_results("w")}
    assert finalized, "the scenario must finalize windows"
    # The scenario must actually exercise late arrivals, not only in-order delivery.
    assert sum(
        w.late_rejected_count + w.out_of_order_accepted_count for w in windows.list_windows()
    )
    assert recorded == finalized, "every finalized window must have an analyzed or skipped result"
