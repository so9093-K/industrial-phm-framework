"""Recorded exports must not assign physical units to an unprofiled archive."""

from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
from tools.aihub.reference import prepare_reference


def test_unprofiled_reference_fails_before_creating_a_meaning_bound_csv(tmp_path: Path) -> None:
    archive = tmp_path / "unprofiled.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("SourceData_211.json", '{"DEVICE_ID":2297,"DEVICE_BD_ID":1,"data":[]}')
    binding = PowerHistoryBinding(
        source_id="recorded",
        asset_id="research-only",
        device_id="2297",
        device_board_id="1",
        timezone="Asia/Seoul",
        identity_evidence="configured grouping",
        timezone_evidence="explicit assumption; unverified",
        version="research-v1",
    )
    output = tmp_path / "reference"
    with pytest.raises(ValueError, match="confirmed semantics"):
        prepare_reference(
            archive,
            "SourceData_211.json",
            binding,
            datetime(2020, 11, 13),
            datetime(2020, 11, 13, 1),
            output,
        )
    assert not output.exists()
