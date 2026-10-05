"""AI-Hub 239 test support shared by integration tests that use synthetic archives."""

from pathlib import Path

import pytest

from industrial_phm.adapters import aihub_power_history
from industrial_phm.adapters.aihub_power import archive_sha256


def treat_archive_as_profiled(monkeypatch: pytest.MonkeyPatch, archive: Path) -> str:
    """Put a synthetic archive inside the semantics-v3 profiled scope for one test.

    Synthetic archives are fail-closed by design; tests that exercise confirmed
    meanings must say explicitly that they pretend the archive was profiled.
    """
    digest = archive_sha256(archive)
    monkeypatch.setitem(
        aihub_power_history._V3_PROFILED_ARCHIVES,
        digest,
        "synthetic test archive treated as profiled",
    )
    return digest
