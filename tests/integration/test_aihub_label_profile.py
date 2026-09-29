import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

pytest.importorskip("ijson")


def _load_tool():
    path = Path(__file__).parents[2] / "tools" / "aihub" / "label_profile.py"
    spec = importlib.util.spec_from_file_location("aihub_label_profile_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_label_profile_reports_labels_metadata_and_ranges_without_masked_contact(tmp_path):
    record = {"ITEM_NAME": "전류평균", "TIMESTAMP": "2020-10-24 00:00:32"}
    payload = {
        "SVC_NAME": "SOH",
        "DEVICE_ID": 1385,
        "KEPCO_INFO": "05-****-****",
        "facility_volt": 380,
        "data": [
            {**record, "ITEM_VALUE": 2.0, "LABEL_NAME": "정상"},
            {**record, "ITEM_NAME": "온도", "ITEM_VALUE": None, "LABEL_NAME": "정상"},
            {**record, "TIMESTAMP": "2020-10-24 00:01:32", "ITEM_VALUE": 4.0, "LABEL_NAME": "경고"},
            {**record, "TIMESTAMP": "2020-10-24 00:01:32", "ITEM_VALUE": 6.0, "LABEL_NAME": "정상"},
        ],
    }
    archive = tmp_path / "label.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("5.보일러/2.SOH진단/a.json", json.dumps(payload, ensure_ascii=False))

    result = _load_tool().profile_label_archive(archive)

    member = result["members"][0]
    assert member["header"] == {"SVC_NAME": "SOH", "DEVICE_ID": 1385, "facility_volt": 380}
    assert member["record_count"] == 4
    assert member["label_counts"] == {"정상": 3, "경고": 1}
    # Labels are record-level facts; one timestamp may carry different labels.
    assert member["timestamps_with_multiple_labels"] == 1
    assert member["record_order_label_transitions"] == 2
    assert member["null_counts"] == {"온도": 1}
    assert member["value_ranges"]["전류평균"] == {"min": 2.0, "max": 6.0, "mean": 4.0}
    assert (member["start"], member["end"]) == ("2020-10-24 00:00:32", "2020-10-24 00:01:32")
