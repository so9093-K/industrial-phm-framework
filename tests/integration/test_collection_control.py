import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    CollectionDesiredState,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    request_collection_state,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import (
    CollectionServicePolicy,
    SqliteCollectionControlRepository,
    run_collection_service,
)

BASE = datetime(2026, 9, 28, 7, 0, tzinfo=UTC)


def _repository(path: Path) -> JsonSourceRepository:
    repository = JsonSourceRepository(path)
    repository.register(
        RegisteredSource(
            source_id="source-a",
            name="Pump OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="pump-01",
                measurement_point_id="drive-end",
                node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=vibration_x"),),
            ),
            registered_at=BASE,
        )
    )
    return repository


def test_collection_control_is_restart_safe_and_separate_from_lifecycle(
    tmp_path: Path,
) -> None:
    source_repository = _repository(tmp_path / "sources.json")
    control_path = tmp_path / "collection-control.sqlite"
    control = SqliteCollectionControlRepository(control_path)

    with pytest.raises(ValueError, match="requires source lifecycle ACTIVE"):
        request_collection_state(
            source_repository,
            source_repository,
            control,
            "source-a",
            CollectionDesiredState.RUNNING,
            requested_at=BASE + timedelta(seconds=1),
        )

    transition_source_lifecycle(
        source_repository,
        "source-a",
        SourceLifecycleState.ACTIVE,
        changed_at=BASE + timedelta(seconds=2),
    )
    running = request_collection_state(
        source_repository,
        source_repository,
        control,
        "source-a",
        CollectionDesiredState.RUNNING,
        requested_at=BASE + timedelta(seconds=3),
    )
    assert running.generation == 1
    assert source_repository.get_lifecycle("source-a").state == SourceLifecycleState.ACTIVE

    repeated = request_collection_state(
        source_repository,
        source_repository,
        control,
        "source-a",
        CollectionDesiredState.RUNNING,
        requested_at=BASE + timedelta(seconds=4),
    )
    assert repeated == running

    stopped = request_collection_state(
        source_repository,
        source_repository,
        control,
        "source-a",
        CollectionDesiredState.STOPPED,
        requested_at=BASE + timedelta(seconds=5),
    )
    assert stopped.generation == 2
    assert source_repository.get_lifecycle("source-a").state == SourceLifecycleState.ACTIVE

    restored = SqliteCollectionControlRepository(control_path)
    assert restored.get("source-a") == stopped
    assert restored.list_records() == (stopped,)


def test_collection_service_owns_runtime_tasks_outside_control_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        source_repository = _repository(tmp_path / "sources.json")
        transition_source_lifecycle(
            source_repository,
            "source-a",
            SourceLifecycleState.ACTIVE,
            changed_at=BASE + timedelta(seconds=1),
        )
        control = SqliteCollectionControlRepository(tmp_path / "collection-control.sqlite")
        request_collection_state(
            source_repository,
            source_repository,
            control,
            "source-a",
            CollectionDesiredState.RUNNING,
            requested_at=BASE + timedelta(seconds=2),
        )

        worker_starts: list[str] = []
        worker_stops: list[str] = []
        window_starts: list[str] = []
        writer_started = asyncio.Event()

        async def _fake_worker(*args, source_id: str | None = None, **kwargs):
            del args
            actual_source_id = source_id or kwargs.get("source_id")
            if actual_source_id is None:
                # source_id is positional in the real call.
                actual_source_id = kwargs.get("_source_id")
            stop_event = kwargs["stop_event"]
            worker_starts.append("source-a")
            await stop_event.wait()
            worker_stops.append("source-a")
            return object()

        async def _fake_window(*args, **kwargs):
            del args
            stop_event = kwargs["stop_event"]
            window_starts.append("source-a")
            await stop_event.wait()
            return object()

        async def _fake_writer(*args, **kwargs):
            del args
            writer_started.set()
            await kwargs["stop_event"].wait()
            return object()

        import industrial_phm.runtime.collection_service as service_module

        monkeypatch.setattr(
            service_module,
            "run_registered_opcua_acquisition_worker",
            _fake_worker,
        )
        monkeypatch.setattr(
            service_module,
            "run_continuous_registered_opcua_observation_windows",
            _fake_window,
        )
        monkeypatch.setattr(
            service_module,
            "run_spool_to_history_writer",
            _fake_writer,
        )

        service_stop = asyncio.Event()
        service = asyncio.create_task(
            run_collection_service(
                source_repository,
                source_repository,
                control,
                object(),
                object(),
                object(),
                object(),
                object(),
                stop_event=service_stop,
                policy=CollectionServicePolicy(reconcile_interval_seconds=0.01),
            )
        )
        await writer_started.wait()

        async def _wait_for(predicate) -> None:
            for _ in range(1000):
                if predicate():
                    return
                await asyncio.sleep(0.001)
            raise AssertionError("condition was not reached")

        await _wait_for(lambda: len(worker_starts) == 1 and len(window_starts) == 1)

        request_collection_state(
            source_repository,
            source_repository,
            control,
            "source-a",
            CollectionDesiredState.STOPPED,
            requested_at=BASE + timedelta(seconds=3),
        )
        await _wait_for(lambda: len(worker_stops) == 1)
        assert not service.done()

        request_collection_state(
            source_repository,
            source_repository,
            control,
            "source-a",
            CollectionDesiredState.RUNNING,
            requested_at=BASE + timedelta(seconds=4),
        )
        await _wait_for(lambda: len(worker_starts) == 2)

        service_stop.set()
        result = await service
        assert result.source_start_count == 2
        assert result.source_stop_count == 2
        assert result.source_restart_count == 1

    asyncio.run(_run())
