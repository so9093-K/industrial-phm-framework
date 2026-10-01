import pytest

from industrial_phm.cli import build_parser, main


def test_doctor_reports_environment_and_next_action(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "industrial-phm 0.0.1" in output
    assert "python:" in output
    assert "project checkout: detected" in output
    assert "data root:" in output
    assert "research UI runtime:" in output
    assert "deep-learning runtime:" in output
    assert "next:" in output
    assert "marimo run apps/analysis_explorer.py" in output


def test_phase_unbalance_result_migration_command_has_explicit_paths() -> None:
    args = build_parser().parse_args(
        [
            "operations",
            "migrate-phase-unbalance-results",
            "--from-json",
            "legacy.json",
            "--to-sqlite",
            "results.sqlite",
        ]
    )
    assert args.from_json.name == "legacy.json"
    assert args.to_sqlite.name == "results.sqlite"


def test_compact_history_command_requires_explicit_work_bound() -> None:
    args = build_parser().parse_args(
        [
            "operations",
            "compact-history",
            "--ducklake-catalog",
            "catalog.sqlite",
            "--ducklake-data",
            "data",
            "--max-compacted-files",
            "32",
            "--max-file-size-bytes",
            "1048576",
        ]
    )
    assert args.ducklake_catalog.name == "catalog.sqlite"
    assert args.ducklake_data.name == "data"
    assert args.max_compacted_files == 32
    assert args.max_file_size_bytes == 1048576
