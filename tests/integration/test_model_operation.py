"""A model's excesses are counted per operating level beside its reference period's mix."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_operation import model_operation

BASE = datetime(2026, 10, 14, tzinfo=UTC)


def test_windows_at_a_level_the_reference_never_held_are_counted_apart(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    current = json.dumps(
        {"semantics": {"definition": {"observed_property": "phase current", "unit": "A"}}}
    )
    # The first hour runs near 60 A, the second near 30 A, the third near 60 A again.
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:model:{'a' * 64}:{index}",
                source_id="comp-file",
                asset_id="comp-01",
                channel_id="전류",
                source_file="comp.csv",
                source_sha256="a" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=(30.0 if 60 <= index < 120 else 60.0) + (index % 3) * 0.2,
                source_metadata_json=current,
            )
            for index in range(180)
        ),
        batch_id="model",
    )
    # Ten-minute windows; those at 30 A all go over the threshold, one at 60 A does too.
    windows = [
        (
            BASE + timedelta(minutes=10 * step),
            BASE + timedelta(minutes=10 * (step + 1)),
            6 <= step < 12 or step == 14,
        )
        for step in range(18)
    ]
    found = model_operation(
        history,
        "comp-01",
        source_id="comp-file",
        point_id=None,
        windows=windows,
        reference=(BASE, BASE + timedelta(hours=1)),
    )
    assert found is not None and found["label"] == "전류"
    assert len(found["levels"]) == 2
    assert found["reference"]["shares"] == [0.0, 0.0, 1.0]
    assert found["windows"] == [
        {"band": 1, "count": 6, "exceeded": 6},
        {"band": 2, "count": 12, "exceeded": 1},
    ]
    assert found["unplaced"] == 0
    # Windows of unequal length cannot be placed one per bucket, so none is placed.
    uneven = [*windows[:-1], (windows[-1][0], windows[-1][1] + timedelta(minutes=1), False)]
    found = model_operation(
        history, "comp-01", source_id="comp-file", point_id=None, windows=uneven, reference=None
    )
    assert found is not None and found["windows"] == [] and found["unplaced"] == 18
    assert found["reference"] is None
