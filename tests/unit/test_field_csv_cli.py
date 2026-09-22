from pathlib import Path

import pytest

from industrial_phm.cli import main


def _write_csv(tmp_path: Path, content: str) -> Path:
    source = tmp_path / "sensor.csv"
    source.write_text(content, encoding="utf-8")
    return source


def test_validate_csv_cli_reports_canonical_readiness(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_csv(
        tmp_path,
        "vibration_x,vibration_y\n1.0,2.0\n2.0,3.0\n3.0,4.0\n",
    )

    exit_code = main(
        [
            "data",
            "validate-csv",
            "--source",
            str(source),
            "--asset-id",
            "pump-01",
            "--channel",
            "vibration_x",
            "--channel",
            "vibration_y",
            "--sampling-rate-hz",
            "12800",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "source kind: field-csv" in captured.out
    assert "asset: pump-01" in captured.out
    assert "samples: 3" in captured.out
    assert "channels: vibration_x, vibration_y" in captured.out
    assert "sampling rate hz: 12800" in captured.out
    assert "sha256:" in captured.out
    assert "quality state: PASS" in captured.out
    assert "canonical mapping: READY" in captured.out
    assert "no model fitting or thresholding performed" in captured.out
    assert captured.err == ""


def test_validate_csv_cli_reports_quality_warning_without_failing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_csv(
        tmp_path,
        "timestamp,vibration\n"
        "2026-09-22T10:00:00+09:00,1.0\n"
        "2026-09-22T10:00:01+09:00,2.0\n"
        "2026-09-22T10:00:02+09:00,3.0\n",
    )

    exit_code = main(
        [
            "data",
            "validate-csv",
            "--source",
            str(source),
            "--asset-id",
            "pump-01",
            "--channel",
            "vibration",
            "--timestamp-column",
            "timestamp",
            "--sampling-rate-hz",
            "2",
            "--sampling-rate-tolerance-ratio",
            "0.05",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "quality state: WARN" in captured.out
    assert "[sampling-rate-mismatch]" in captured.out
    assert "maximum sampling interval deviation ratio: 1" in captured.out
    assert captured.err == ""


def test_validate_csv_cli_rejects_missing_time_basis(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_csv(tmp_path, "vibration\n1.0\n")

    exit_code = main(
        [
            "data",
            "validate-csv",
            "--source",
            str(source),
            "--asset-id",
            "pump-01",
            "--channel",
            "vibration",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "field CSV validation failed:" in captured.err
    assert "timestamp_column or sampling_rate_hz" in captured.err
