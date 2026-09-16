from pathlib import Path

import pytest

from industrial_phm.cli import main
from industrial_phm.data.acquisition import ManualAcquisitionRequired, fetch_dataset
from industrial_phm.data.registry import get_dataset, list_datasets
from industrial_phm.data.validation import DatasetIntegrityError, inspect_file, verify_sha256


def test_registry_exposes_primary_and_smoke_datasets() -> None:
    manifests = {manifest.dataset_id: manifest for manifest in list_datasets()}

    assert set(manifests) >= {"xjtu-sy", "ai4i-2020"}
    assert manifests["xjtu-sy"].provider == "manual"
    assert manifests["ai4i-2020"].provider == "url"


def test_manual_source_never_triggers_implicit_network_fetch(tmp_path: Path) -> None:
    manifest = get_dataset("xjtu-sy")

    with pytest.raises(ManualAcquisitionRequired):
        fetch_dataset(manifest, tmp_path)


def test_file_integrity_reports_and_verifies_sha256(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"industrial-phm")

    integrity = inspect_file(path)

    assert integrity.size_bytes == len(b"industrial-phm")
    assert verify_sha256(path, integrity.sha256) == integrity

    with pytest.raises(DatasetIntegrityError, match="checksum mismatch"):
        verify_sha256(path, "0" * 64)


def test_cli_lists_registered_datasets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["data", "list"]) == 0

    output = capsys.readouterr().out
    assert "xjtu-sy" in output
    assert "ai4i-2020" in output
