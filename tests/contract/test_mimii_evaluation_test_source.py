import struct
import wave
from pathlib import Path

import pytest

from industrial_phm.adapters import (
    MimiiDueSourceError,
    iter_mimii_evaluation_test_clips,
    read_mimii_evaluation_test_series,
    validate_mimii_evaluation_test_source,
)

_FRAMES = 160_000


def _write_clip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(struct.pack("<h", 0) * _FRAMES)


def _source(root: Path, *, clips_per_scope: int = 1) -> Path:
    source = root / "audio"
    for machine in ("fan", "gearbox", "pump", "slider", "valve"):
        for section in ("03", "04", "05"):
            for domain in ("source", "target"):
                for index in range(clips_per_scope):
                    _write_clip(
                        source
                        / machine
                        / f"{domain}_test"
                        / f"section_{section}_{domain}_test_{index:04d}.wav"
                    )
    return source


def test_evaluation_test_source_validates_label_free_profile(tmp_path: Path) -> None:
    report = validate_mimii_evaluation_test_source(_source(tmp_path), full=True)

    assert report.profile_matches
    assert report.machine_count == 5
    assert report.section_count == 3
    assert report.clip_count == 30
    assert report.checked_wav_count == 30
    assert report.sampling_rate_hz == 16_000.0
    assert report.frames_per_clip == _FRAMES


def test_evaluation_test_clip_record_carries_no_label(tmp_path: Path) -> None:
    """A scorer reading this source must not be able to recover a clip label."""
    source = _source(tmp_path)

    clip = iter_mimii_evaluation_test_clips(source, machine_type="fan", section="03")[0]
    series = read_mimii_evaluation_test_series(source, clip)

    assert not hasattr(clip, "label")
    assert not any("label" in key for key in series.metadata)
    assert series.labels is None
    assert series.metadata["split"] == "test"
    assert series.metadata["source_group"] == "eval"


def test_evaluation_test_source_rejects_development_filename_grammar(tmp_path: Path) -> None:
    """Dev filenames carry normal/anomaly; accepting them here would leak labels."""
    source = _source(tmp_path)
    _write_clip(source / "fan" / "source_test" / "section_03_source_test_normal_0001.wav")

    with pytest.raises(MimiiDueSourceError, match="evaluation-test filename grammar"):
        validate_mimii_evaluation_test_source(source)


def test_evaluation_test_source_rejects_development_sections(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _write_clip(source / "fan" / "source_test" / "section_00_source_test_0001.wav")

    with pytest.raises(MimiiDueSourceError, match="evaluation-test section"):
        validate_mimii_evaluation_test_source(source)


def test_evaluation_test_source_rejects_domain_directory_mismatch(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _write_clip(source / "fan" / "source_test" / "section_03_target_test_0001.wav")

    with pytest.raises(MimiiDueSourceError, match="declares domain"):
        validate_mimii_evaluation_test_source(source)


def test_evaluation_test_scope_selection_is_deterministic(tmp_path: Path) -> None:
    source = _source(tmp_path, clips_per_scope=3)

    clips = iter_mimii_evaluation_test_clips(
        source, machine_type="slider", section="05", domain="target"
    )

    assert [clip.clip_number for clip in clips] == [0, 1, 2]
    assert {clip.machine for clip in clips} == {"slider"}
    assert {clip.domain for clip in clips} == {"target"}


def test_evaluation_test_scope_rejects_unknown_requests(tmp_path: Path) -> None:
    source = _source(tmp_path)

    with pytest.raises(MimiiDueSourceError, match="machine type"):
        iter_mimii_evaluation_test_clips(source, machine_type="toycar")
    with pytest.raises(MimiiDueSourceError, match="evaluation section"):
        iter_mimii_evaluation_test_clips(source, section="00")
