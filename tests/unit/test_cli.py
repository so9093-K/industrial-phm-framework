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
    assert "start Operations: make up" in output
    assert "open the printed operations_url" in output
    assert "first use: register your CSV or start the isolated sample in Web" in output
    assert "marimo run" not in output


def test_doctor_guides_installed_cli_when_not_in_checkout(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "project checkout: not detected" in output
    assert "industrial-phm operations up artifacts/operations" in output
    assert "requires the operations extra and a local Linux host" in output
    assert "make up" not in output


def test_removed_phase_result_migration_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["maintenance", "migrate-phase-unbalance-results"])

    assert raised.value.code == 2


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
