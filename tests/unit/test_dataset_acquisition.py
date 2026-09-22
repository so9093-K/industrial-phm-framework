from pathlib import Path
from zipfile import ZipFile

import pytest

from industrial_phm.cli import main
from industrial_phm.data.acquisition import ManualAcquisitionRequired, fetch_dataset
from industrial_phm.data.registry import get_dataset, list_datasets
from industrial_phm.data.validation import (
    DatasetIntegrityError,
    inspect_file,
    inspect_source,
    verify_sha256,
)


def test_registry_exposes_registered_research_datasets() -> None:
    manifests = {manifest.dataset_id: manifest for manifest in list_datasets()}

    assert set(manifests) >= {"xjtu-sy", "ims-bearings", "ai4i-2020", "mimii-due"}
    assert manifests["xjtu-sy"].provider == "manual"
    assert manifests["ims-bearings"].provider == "url"
    assert manifests["ims-bearings"].sha256 is None
    assert manifests["ai4i-2020"].provider == "url"
    assert manifests["mimii-due"].provider == "manual"
    assert manifests["mimii-due"].citation_doi == "10.5281/zenodo.4740355"
    assert "CC BY-NC-SA 4.0" in manifests["mimii-due"].license_name


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


def test_cli_verify_without_pinned_checksum_reports_local_provenance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = get_dataset("ims-bearings")
    assert manifest.archive_name is not None
    archive_path = tmp_path / manifest.dataset_id / manifest.archive_name
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(b"local-ims-placeholder")

    assert main(["data", "verify", "ims-bearings", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert f"local file inspected: {archive_path}" in output
    assert "verified local file:" not in output
    assert "integrity basis: local SHA-256 provenance; no publisher checksum pinned" in output


def test_source_inspection_summarizes_nested_directory(tmp_path: Path) -> None:
    nested = tmp_path / "bearing" / "run"
    nested.mkdir(parents=True)
    (tmp_path / "metadata.txt").write_text("meta", encoding="utf-8")
    (nested / "sample.csv").write_bytes(b"1,2\n3,4\n")

    inspection = inspect_source(tmp_path)

    assert inspection.kind == "directory"
    assert inspection.file_count == 2
    assert inspection.source_bytes == len(b"meta") + len(b"1,2\n3,4\n")
    assert inspection.total_bytes == inspection.source_bytes
    assert inspection.max_depth == 3
    assert [(item.extension, item.file_count) for item in inspection.extension_summaries] == [
        (".csv", 1),
        (".txt", 1),
    ]
    assert inspection.top_level_entries == ("bearing", "metadata.txt")
    assert inspection.representative_files == ("bearing/run/sample.csv", "metadata.txt")


def test_source_inspection_bounds_path_samples(tmp_path: Path) -> None:
    for index in range(20):
        asset = tmp_path / f"asset-{index:02d}"
        asset.mkdir()
        (asset / "sample.dat").write_text(str(index), encoding="utf-8")

    inspection = inspect_source(tmp_path)

    assert inspection.file_count == 20
    assert inspection.top_level_entries == tuple(f"asset-{index:02d}" for index in range(12))
    assert len(inspection.representative_files) == 12


def test_source_inspection_reads_zip_metadata_without_member_payloads(tmp_path: Path) -> None:
    archive_path = tmp_path / "ims.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("1st_test/2003.10.22.12.06.24", "sensitive-value\n")
        archive.writestr("2nd_test/2004.02.12.10.32.39", "another-value\n")
        archive.writestr("README.txt", "metadata\n")

    inspection = inspect_source(archive_path)

    assert inspection.kind == "zip"
    assert inspection.file_count == 3
    assert inspection.source_bytes == archive_path.stat().st_size
    assert inspection.total_bytes == len(b"sensitive-value\n") + len(b"another-value\n") + len(
        b"metadata\n"
    )
    assert inspection.max_depth == 2
    assert [(item.extension, item.file_count) for item in inspection.extension_summaries] == [
        ("", 2),
        (".txt", 1),
    ]
    assert inspection.top_level_entries == ("1st_test", "2nd_test", "README.txt")


def test_source_inspection_rejects_invalid_zip_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "broken.zip"
    archive_path.write_text("not a zip", encoding="utf-8")

    with pytest.raises(DatasetIntegrityError, match="ZIP archive is not readable"):
        inspect_source(archive_path)


def test_cli_lists_registered_datasets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["data", "list"]) == 0

    output = capsys.readouterr().out
    assert "xjtu-sy" in output
    assert "ims-bearings" in output
    assert "ai4i-2020" in output


def test_cli_inspects_manual_dataset_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "bearing.csv").write_bytes(b"sample")

    assert main(["data", "inspect", "xjtu-sy", "--source", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "dataset: xjtu-sy" in output
    assert f"local source: {tmp_path}" in output
    assert "source kind: directory" in output
    assert "files: 1" in output
    assert "extension .csv: 1 file(s)" in output
    assert "representative file:" not in output
    assert "inspection scope: structural inventory" in output
    assert "inspection state: completed" in output


def test_cli_inspects_zip_structure_without_printing_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_path = tmp_path / "ims.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("1st_test/2003.10.22.12.06.24", "sensitive-value\n")
        archive.writestr("2nd_test/2004.02.12.10.32.39", "another-value\n")

    assert (
        main(
            [
                "data",
                "inspect",
                "ims-bearings",
                "--source",
                str(archive_path),
                "--details",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "source kind: zip" in output
    assert "files: 2" in output
    assert "uncompressed bytes:" in output
    assert "extension <none>: 2 file(s)" in output
    assert "top-level sample: 1st_test" in output
    assert "representative file: 1st_test/2003.10.22.12.06.24" in output
    assert "inspection scope: structural inventory" in output
    assert "inspection state: completed" in output
    assert "prepared source state:" not in output
    assert "sensitive-value" not in output


def test_cli_inspection_reports_nested_archive_preparation_requirement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_path = tmp_path / "ims.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("4. Bearings/IMS.7z", "nested-archive-placeholder")

    assert (
        main(
            [
                "data",
                "inspect",
                "ims-bearings",
                "--source",
                str(archive_path),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "extension .7z: 1 file(s)" in output
    assert "inspection state: completed" in output
    assert "prepared source state: nested archive extraction required" in output
    assert "next: extract the nested archive as described in data/README.md" in output
    assert "then: industrial-phm data validate ims-bearings" in output


def test_cli_rejects_empty_dataset_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["data", "inspect", "xjtu-sy", "--source", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    assert "files: 0" in captured.out
    assert "empty local source" in captured.err


def test_cli_status_guides_manual_dataset_to_preparation_docs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["data", "status", "xjtu-sy", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "local state: manual source" in output
    assert "next: follow the dataset preparation guide in data/README.md" in output


def test_cli_status_guides_missing_managed_dataset_to_fetch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["data", "status", "ai4i-2020", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "local state: missing" in output
    assert "next: industrial-phm data fetch ai4i-2020" in output


def test_cli_unknown_dataset_lists_available_ids(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["data", "status", "does-not-exist"]) == 2

    error = capsys.readouterr().err
    assert "unknown dataset: does-not-exist" in error
    assert "available datasets:" in error
    assert "xjtu-sy" in error
