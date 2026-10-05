import json
from pathlib import Path

import pytest

from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding

PRESET_DIR = Path(__file__).resolve().parents[2] / "tools" / "opcua" / "presets"
PRESETS = sorted(PRESET_DIR.glob("*.json"))


@pytest.mark.parametrize("path", PRESETS, ids=lambda path: path.stem)
def test_replay_binding_presets_are_explicit_and_unverified(path: Path) -> None:
    binding = PowerHistoryBinding(**json.loads(path.read_text(encoding="utf-8")))
    # A preset is a configured grouping, never a claim about the physical asset or zone.
    assert "unverified" in binding.identity_evidence
    assert "unverified" in binding.timezone_evidence
    assert binding.asset_id in path.stem


def test_air_compressor_reference_preset_matches_the_reference_profile() -> None:
    path = next(p for p in PRESETS if p.stem == "aihub-air-compressor-1338-replay")
    binding = PowerHistoryBinding(**json.loads(path.read_text(encoding="utf-8")))
    assert (binding.device_id, binding.device_board_id) == ("1338", "1")
    assert binding.timezone == "Asia/Seoul"
