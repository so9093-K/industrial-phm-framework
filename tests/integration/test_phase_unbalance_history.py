import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest

from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
from industrial_phm.application.finding_review import (
    JsonOperationalFindingRepository,
    create_human_review_finding,
)
from industrial_phm.application.phase_unbalance import run_phase_unbalance_analysis
from industrial_phm.application.phase_unbalance_state import JsonPhaseUnbalanceRepository
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

pytest.importorskip("ijson")
pytest.importorskip("duckdb")

MEMBER = "보일러/SourceData_347.json"
LOCAL = datetime(2021, 1, 20, 0, 0)


def _import_history():
    path = Path(__file__).parents[2] / "tools" / "aihub" / "history.py"
    spec = importlib.util.spec_from_file_location("aihub_history_tool_pu", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.import_history


def _archive(tmp_path):
    data = []
    for minute in range(4):
        stamp = (LOCAL + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S")
        for phase, volt, amp in (("R", 220, 10), ("S", 230, 10), ("T", 225 + minute, 13)):
            data.append({"ITEM_NAME": f"{phase}상전압", "ITEM_VALUE": volt, "TIMESTAMP": stamp})
            data.append({"ITEM_NAME": f"{phase}상전류", "ITEM_VALUE": amp, "TIMESTAMP": stamp})
    path = tmp_path / "boiler.zip"
    with ZipFile(path, "w") as archive:
        payload = {"DEVICE_ID": 5764, "DEVICE_BD_ID": 1, "data": data}
        archive.writestr(MEMBER, json.dumps(payload, ensure_ascii=False))
    return path


def test_recorded_snapshot_recomputes_identical_evidence_after_more_history(tmp_path):
    import_history = _import_history()
    archive = _archive(tmp_path)
    binding = PowerHistoryBinding(
        source_id="boiler-source",
        asset_id="boiler-asset",
        device_id="5764",
        device_board_id="1",
        timezone="Asia/Seoul",
        identity_evidence="test grouping",
        timezone_evidence="test assumption",
        version="test-v1",
    )
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    import_history(archive, MEMBER, binding, LOCAL, LOCAL + timedelta(minutes=2), history)
    window = {
        "asset_id": "boiler-asset",
        "source_id": "boiler-source",
        "start_at": datetime(2021, 1, 19, 15, tzinfo=UTC),
        "end_at": datetime(2021, 1, 19, 16, tzinfo=UTC),
    }
    first = run_phase_unbalance_analysis(history, **window)
    voltage = first.evidence.results[0]
    assert voltage.evaluated_samples == 2
    assert first.evidence.semantic_versions == ("aihub-239-semantics-v2",)
    assert voltage.max_at.utcoffset() == timedelta(0)

    repository = JsonPhaseUnbalanceRepository(tmp_path / "unbalance.json")
    repository.record(first)
    assert repository.list_results() == (first,)

    # A person can request review of this evidence like any other capability's.
    finding = create_human_review_finding(repository.list_results()[0])
    assert finding.evidence_refs == (first.evidence.evidence_id,)
    assert finding.capability_id == "three-phase-unbalance-v1"
    findings = JsonOperationalFindingRepository(tmp_path / "findings.json")
    findings.record(finding)
    assert findings.list_findings() == (finding,)

    # More history inside the same range must not change a recorded result.
    import_history(
        archive, MEMBER, binding, LOCAL + timedelta(minutes=2), LOCAL + timedelta(hours=1), history
    )
    snapshot = first.evidence.input_reference.snapshot_id
    again = run_phase_unbalance_analysis(history, snapshot_id=snapshot, **window)
    assert again.evidence.results == first.evidence.results
    latest = run_phase_unbalance_analysis(history, **window)
    assert latest.evidence.results[0].evaluated_samples == 4
