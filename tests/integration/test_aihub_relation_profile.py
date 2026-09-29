import importlib.util
import json
import math
from pathlib import Path
from zipfile import ZipFile

import pytest

pytest.importorskip("ijson")


def _load_tool():
    path = Path(__file__).parents[2] / "tools" / "aihub" / "relation_profile.py"
    spec = importlib.util.spec_from_file_location("aihub_relation_profile_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_relation_profile_counts_exclusions_and_reports_ratio_distribution(tmp_path):
    def record(name, value, second):
        return {"ITEM_NAME": name, "ITEM_VALUE": value, "TIMESTAMP": f"2021-01-01 00:00:0{second}"}

    data = [
        record("상전압평균", 220.0, 1),
        record("선간전압평균", 220.0 * math.sqrt(3), 1),
        record("상전압평균", 220.0, 2),
        record("선간전압평균", None, 2),
        # Conflicting values at one timestamp are excluded, never averaged.
        record("상전압평균", 220.0, 3),
        record("상전압평균", 230.0, 3),
        record("선간전압평균", 381.0, 3),
    ]
    archive = tmp_path / "raw.zip"
    payload = {"DEVICE_ID": "1", "DEVICE_BD_ID": "1", "data": data}
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("5.보일러/SourceData_1.json", json.dumps(payload, ensure_ascii=False))

    member = _load_tool().profile_relations(archive)["members"][0]

    assert member["excluded_channel_values"] == {
        "null-channel-values": 1,
        "conflicting-channel-values": 1,
    }
    relation = member["relations"]["line_to_phase_voltage"]
    assert relation["evaluated"] == 1
    assert relation["median"] == pytest.approx(math.sqrt(3))
    assert relation["within_tolerance_fraction"] == 1.0
    assert relation["skipped_timestamps"] == {"missing": 2}
