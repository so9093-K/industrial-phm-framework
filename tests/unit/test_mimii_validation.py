import wave
from pathlib import Path

import pytest

from industrial_phm.adapters import MimiiDueSourceError, validate_mimii_due_source
from industrial_phm.cli import main

_FRAME_COUNT = 160_000


def _write_wav(
    path: Path,
    *,
    sampling_rate_hz: int = 16_000,
    frame_count: int = _FRAME_COUNT,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sampling_rate_hz)
        target.writeframes(b"\x00\x00" * frame_count)


def test_mimii_validator_preserves_filename_grammar_without_normalizing_attributes(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "dev"
        / "fan"
        / "train"
        / "section_00_source_train_normal_0000_strenght_1_ambient.wav"
    )
    _write_wav(path)

    report = validate_mimii_due_source(tmp_path)

    assert report.clip_count == 1
    assert report.train_clip_count == 1
    assert report.test_clip_count == 0
    assert report.checked_wav_count == 1
    assert report.channels == 1
    assert report.sample_width_bits == 16
    assert report.sampling_rate_hz == 16_000.0
    assert report.frames_per_clip == _FRAME_COUNT
    assert report.duration_seconds == 10.0
    assert not report.profile_matches
    assert any("clip count mismatch" in issue for issue in report.profile_issues)


def test_mimii_validator_rejects_directory_filename_semantic_drift(tmp_path: Path) -> None:
    path = tmp_path / "dev" / "pump" / "source_test" / "section_00_target_test_normal_0000.wav"
    _write_wav(path)

    with pytest.raises(MimiiDueSourceError, match="domain does not match directory"):
        validate_mimii_due_source(tmp_path)


def test_mimii_validator_rejects_test_operating_attribute(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "dev"
        / "valve"
        / "target_test"
        / "section_00_target_test_normal_0000_pattern_1_air_pump.wav"
    )
    _write_wav(path)

    with pytest.raises(MimiiDueSourceError, match="test filename must not contain"):
        validate_mimii_due_source(tmp_path)


def test_mimii_validator_rejects_incompatible_wav_header(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "dev"
        / "slider"
        / "train"
        / "section_00_source_train_normal_0000_vel1_dis1_accl1.wav"
    )
    _write_wav(path, sampling_rate_hz=8_000)

    with pytest.raises(MimiiDueSourceError, match="unexpected MIMII DUE WAV profile"):
        validate_mimii_due_source(tmp_path)


def test_mimii_full_validation_checks_every_wav_header(tmp_path: Path) -> None:
    for index in range(4):
        path = (
            tmp_path
            / "dev"
            / "gearbox"
            / "train"
            / f"section_00_source_train_normal_{index:04d}_1_g_1_mm_1_mV_none.wav"
        )
        _write_wav(path)

    sampled = validate_mimii_due_source(tmp_path)
    full = validate_mimii_due_source(tmp_path, full=True)

    assert sampled.checked_wav_count == 3
    assert full.checked_wav_count == 4
    assert not sampled.full
    assert full.full


def test_data_validate_routes_mimii_due_to_dataset_validator(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = (
        tmp_path
        / "dev"
        / "fan"
        / "train"
        / "section_00_source_train_normal_0000_strength_1_ambient.wav"
    )
    _write_wav(path)

    exit_code = main(
        [
            "data",
            "validate",
            "mimii-due",
            "--source",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "dataset: mimii-due" in captured.out
    assert "WAV header compatibility: PASS (sampled)" in captured.out
    assert "profile compatibility: FAIL" in captured.out
    assert "profile issue:" in captured.err
