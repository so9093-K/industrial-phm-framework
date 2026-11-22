"""A long calculation's back-to-back leases do not keep other screens' reads from the catalog."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import phm_workspace


def test_a_short_read_gets_its_turn_between_a_calculations_batches(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    config = DuckLakeAssetHistoryConfig(
        workspace.history_catalog_path,
        workspace.history_data_path,
        catalog_lock_timeout_seconds=2.0,
    )
    DuckLakeAssetHistory(config).initialize()
    calculating, stop = threading.Event(), threading.Event()

    def calculation() -> None:
        # 한 묶음씩 잠금을 쥐었다 놓고 곧바로 다음 묶음을 연다(첫 특이사항 계산처럼).
        history = DuckLakeAssetHistory(config)
        while not stop.is_set():
            connection = history._connect()
            calculating.set()
            time.sleep(0.15)
            connection.close()

    worker = threading.Thread(target=calculation)
    worker.start()
    try:
        assert calculating.wait(timeout=5)
        started = time.monotonic()
        # 다른 화면의 짧은 읽기: 계산이 끝나기를 기다리지 않고 묶음 사이에 차례를 받는다.
        connection = DuckLakeAssetHistory(config)._connect()
        waited = time.monotonic() - started
        connection.close()
    finally:
        stop.set()
        worker.join(timeout=10)
    assert waited < 1.0
