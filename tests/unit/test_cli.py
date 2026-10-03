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
            "maintenance",
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
            "maintenance",
            "history",
            "compact",
            "--ducklake-catalog",
            "catalog.sqlite",
            "--ducklake-data",
            "data",
            "--max-compacted-files",
            "32",
            "--target-file-size-bytes",
            "1048576",
            "--max-file-size-bytes",
            "262144",
        ]
    )
    assert args.ducklake_catalog.name == "catalog.sqlite"
    assert args.ducklake_data.name == "data"
    assert args.max_compacted_files == 32
    assert args.target_file_size_bytes == 1048576
    assert args.max_file_size_bytes == 262144


@pytest.mark.parametrize(
    "argv",
    [
        ["operations", "backup"],
        ["operations", "restore"],
        ["operations", "preflight"],
        ["operations", "compact-history"],
        ["operations", "run-collection-service"],
        ["operations", "run-window-analysis"],
    ],
)
def test_removed_legacy_operational_spellings_are_rejected(
    argv: list[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)

    assert raised.value.code == 2


def test_operations_help_contains_only_normal_node_lifecycle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["operations", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    for command in ("init", "start", "status", "logs", "stop"):
        assert command in output
    for internal in (
        "backup",
        "preflight",
        "compact-history",
        "run-collection-service",
        "run-window-analysis",
    ):
        assert internal not in output


def test_top_level_help_exposes_operational_responsibility_groups(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "operations" in output
    assert "maintenance" in output
    assert "validate" in output
    assert "internal" in output
