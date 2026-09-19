"""MIMII DUE source validation for prepared machine-audio data."""

from __future__ import annotations

import re
import struct
import wave
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from industrial_phm.contracts import CanonicalTimeSeries

_MACHINE_TYPES = ("fan", "gearbox", "pump", "slider", "valve")
_GROUP_SECTIONS = {
    "dev": ("00", "01", "02"),
    "eval": ("03", "04", "05"),
}
_GROUP_DIRECTORIES = {
    "dev": ("train", "source_test", "target_test"),
    "eval": ("train",),
}
MIMII_DUE_CHANNELS = ("pcm_amplitude",)

_CHANNEL_COUNT = len(MIMII_DUE_CHANNELS)
_SAMPLE_WIDTH_BITS = 16
_SAMPLING_RATE_HZ = 16_000.0
_FRAMES_PER_CLIP = 160_000
_DURATION_SECONDS = 10.0

_FILENAME_PATTERN = re.compile(
    r"^section_(?P<section>\d{2})_"
    r"(?P<domain>source|target)_"
    r"(?P<split>train|test)_"
    r"(?P<label>normal|anomaly)_"
    r"(?P<clip_number>\d{4})"
    r"(?:_(?P<raw_attribute>.+))?\.wav$"
)

_EXPECTED_COUNTS = {
    ("dev", "fan", "source", "train", "normal"): 3_000,
    ("dev", "fan", "source", "train", "anomaly"): 0,
    ("dev", "fan", "target", "train", "normal"): 9,
    ("dev", "fan", "target", "train", "anomaly"): 0,
    ("dev", "fan", "source", "test", "normal"): 300,
    ("dev", "fan", "source", "test", "anomaly"): 300,
    ("dev", "fan", "target", "test", "normal"): 300,
    ("dev", "fan", "target", "test", "anomaly"): 300,
    ("dev", "gearbox", "source", "train", "normal"): 3_017,
    ("dev", "gearbox", "source", "train", "anomaly"): 0,
    ("dev", "gearbox", "target", "train", "normal"): 9,
    ("dev", "gearbox", "target", "train", "anomaly"): 0,
    ("dev", "gearbox", "source", "test", "normal"): 411,
    ("dev", "gearbox", "source", "test", "anomaly"): 351,
    ("dev", "gearbox", "target", "test", "normal"): 309,
    ("dev", "gearbox", "target", "test", "anomaly"): 336,
    ("dev", "pump", "source", "train", "normal"): 3_000,
    ("dev", "pump", "source", "train", "anomaly"): 0,
    ("dev", "pump", "target", "train", "normal"): 9,
    ("dev", "pump", "target", "train", "anomaly"): 0,
    ("dev", "pump", "source", "test", "normal"): 300,
    ("dev", "pump", "source", "test", "anomaly"): 300,
    ("dev", "pump", "target", "test", "normal"): 300,
    ("dev", "pump", "target", "test", "anomaly"): 300,
    ("dev", "slider", "source", "train", "normal"): 3_000,
    ("dev", "slider", "source", "train", "anomaly"): 0,
    ("dev", "slider", "target", "train", "normal"): 9,
    ("dev", "slider", "target", "train", "anomaly"): 0,
    ("dev", "slider", "source", "test", "normal"): 310,
    ("dev", "slider", "source", "test", "anomaly"): 302,
    ("dev", "slider", "target", "test", "normal"): 300,
    ("dev", "slider", "target", "test", "anomaly"): 302,
    ("dev", "valve", "source", "train", "normal"): 3_000,
    ("dev", "valve", "source", "train", "anomaly"): 0,
    ("dev", "valve", "target", "train", "normal"): 9,
    ("dev", "valve", "target", "train", "anomaly"): 0,
    ("dev", "valve", "source", "test", "normal"): 300,
    ("dev", "valve", "source", "test", "anomaly"): 300,
    ("dev", "valve", "target", "test", "normal"): 300,
    ("dev", "valve", "target", "test", "anomaly"): 300,
    ("eval", "fan", "source", "train", "normal"): 3_000,
    ("eval", "fan", "source", "train", "anomaly"): 0,
    ("eval", "fan", "target", "train", "normal"): 9,
    ("eval", "fan", "target", "train", "anomaly"): 0,
    ("eval", "gearbox", "source", "train", "normal"): 3_105,
    ("eval", "gearbox", "source", "train", "anomaly"): 0,
    ("eval", "gearbox", "target", "train", "normal"): 9,
    ("eval", "gearbox", "target", "train", "anomaly"): 0,
    ("eval", "pump", "source", "train", "normal"): 3_000,
    ("eval", "pump", "source", "train", "anomaly"): 0,
    ("eval", "pump", "target", "train", "normal"): 9,
    ("eval", "pump", "target", "train", "anomaly"): 0,
    ("eval", "slider", "source", "train", "normal"): 3_000,
    ("eval", "slider", "source", "train", "anomaly"): 0,
    ("eval", "slider", "target", "train", "normal"): 9,
    ("eval", "slider", "target", "train", "anomaly"): 0,
    ("eval", "valve", "source", "train", "normal"): 3_000,
    ("eval", "valve", "source", "train", "anomaly"): 0,
    ("eval", "valve", "target", "train", "normal"): 9,
    ("eval", "valve", "target", "train", "anomaly"): 0,
}


class MimiiDueSourceError(ValueError):
    """Raised when a prepared MIMII DUE source violates the observed source grammar."""


@dataclass(frozen=True, slots=True)
class MimiiDueValidationReport:
    """Dataset-specific compatibility summary for a prepared MIMII DUE source."""

    source: Path
    full: bool
    machine_count: int
    section_count: int
    clip_count: int
    train_clip_count: int
    test_clip_count: int
    checked_wav_count: int
    channels: int
    sample_width_bits: int
    sampling_rate_hz: float
    frames_per_clip: int
    duration_seconds: float
    profile_issues: tuple[str, ...]

    @property
    def profile_matches(self) -> bool:
        """Return whether the source matches the observed MIMII DUE v1.01 profile."""
        return not self.profile_issues


@dataclass(frozen=True, slots=True)
class _MimiiDueClip:
    path: Path
    group: str
    machine: str
    section: str
    domain: str
    split: str
    label: str
    clip_number: int
    raw_attribute: str | None


class MimiiDueAdapter:
    """Yield one canonical audio waveform segment for each MIMII DUE WAV clip."""

    @property
    def domain(self) -> str:
        """Return the stable dataset/domain identifier."""
        return "mimii-due"

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        """Read prepared MIMII DUE clips lazily without preprocessing PCM amplitude."""
        clips = _collect_clips(source)
        if not clips:
            raise MimiiDueSourceError(f"MIMII DUE source contains no WAV clips: {source}")

        for clip in clips:
            yield _canonical_series(source, clip)


def _canonical_series(source: Path, clip: _MimiiDueClip) -> CanonicalTimeSeries:
    values = _read_wav_values(clip.path)
    return CanonicalTimeSeries(
        asset_id=f"{clip.machine}/section-{clip.section}",
        timestamps=None,
        channels=MIMII_DUE_CHANNELS,
        values=values,
        sampling_rate_hz=_SAMPLING_RATE_HZ,
        metadata={
            "dataset_id": "mimii-due",
            "source_group": clip.group,
            "machine_type": clip.machine,
            "section": clip.section,
            "domain": clip.domain,
            "split": clip.split,
            "clip_label": clip.label,
            "source_file_number": clip.clip_number,
            "raw_attribute": clip.raw_attribute,
            "sample_encoding": "pcm-s16le",
            "sample_width_bits": _SAMPLE_WIDTH_BITS,
            "source_file": clip.path.relative_to(source).as_posix(),
        },
    )


def validate_mimii_due_source(
    source: Path,
    *,
    full: bool = False,
) -> MimiiDueValidationReport:
    """Validate prepared MIMII DUE structure, filename grammar, counts, and WAV headers.

    Structural and filename validation always covers every visible source file. By
    default WAV compatibility is checked on representative clips from each observed
    group/machine/domain/split/label stratum. full=True checks every WAV header.

    This function validates compatibility with the source profile. It does not decode
    waveform payloads or perform preprocessing such as PCM amplitude normalization.
    """
    clips = _collect_clips(source)
    if not clips:
        raise MimiiDueSourceError(f"MIMII DUE source contains no WAV clips: {source}")

    selected = _validation_clips(clips, full=full)
    for clip in selected:
        _validate_wav_header(clip.path)

    observed_counts: Counter[tuple[str, str, str, str, str]] = Counter(
        (clip.group, clip.machine, clip.domain, clip.split, clip.label) for clip in clips
    )
    sections = {(clip.group, clip.section) for clip in clips}
    machines = {clip.machine for clip in clips}

    return MimiiDueValidationReport(
        source=source,
        full=full,
        machine_count=len(machines),
        section_count=len(sections),
        clip_count=len(clips),
        train_clip_count=sum(clip.split == "train" for clip in clips),
        test_clip_count=sum(clip.split == "test" for clip in clips),
        checked_wav_count=len(selected),
        channels=_CHANNEL_COUNT,
        sample_width_bits=_SAMPLE_WIDTH_BITS,
        sampling_rate_hz=_SAMPLING_RATE_HZ,
        frames_per_clip=_FRAMES_PER_CLIP,
        duration_seconds=_DURATION_SECONDS,
        profile_issues=_profile_issues(source, observed_counts),
    )


def _collect_clips(source: Path) -> tuple[_MimiiDueClip, ...]:
    if not source.is_dir():
        raise MimiiDueSourceError(f"MIMII DUE source directory does not exist: {source}")

    clips: list[_MimiiDueClip] = []
    for group, directory_names in _GROUP_DIRECTORIES.items():
        for machine in _MACHINE_TYPES:
            machine_dir = source / group / machine
            if not machine_dir.is_dir():
                continue
            for directory_name in directory_names:
                directory = machine_dir / directory_name
                if not directory.is_dir():
                    continue
                for path in sorted(directory.iterdir(), key=lambda item: item.name):
                    if path.name.startswith("."):
                        continue
                    if not path.is_file():
                        raise MimiiDueSourceError(
                            f"unexpected MIMII DUE entry inside clip directory: {path}"
                        )
                    clips.append(
                        _parse_clip_path(
                            path=path,
                            group=group,
                            machine=machine,
                            directory_name=directory_name,
                        )
                    )

    clips.sort(key=lambda clip: clip.path.relative_to(source).as_posix())
    return tuple(clips)


def _parse_clip_path(
    *,
    path: Path,
    group: str,
    machine: str,
    directory_name: str,
) -> _MimiiDueClip:
    match = _FILENAME_PATTERN.fullmatch(path.name)
    if match is None:
        raise MimiiDueSourceError(f"unexpected MIMII DUE filename grammar: {path.name!r}")

    section = match.group("section")
    domain = match.group("domain")
    split = match.group("split")
    label = match.group("label")
    clip_number = int(match.group("clip_number"))
    raw_attribute = match.group("raw_attribute")

    expected_sections = _GROUP_SECTIONS[group]
    if section not in expected_sections:
        raise MimiiDueSourceError(
            f"unexpected MIMII DUE section for {group}: {section!r}; "
            f"expected one of {expected_sections}"
        )

    if directory_name == "train":
        expected_split = "train"
        expected_domain = None
    elif directory_name == "source_test":
        expected_split = "test"
        expected_domain = "source"
    elif directory_name == "target_test":
        expected_split = "test"
        expected_domain = "target"
    else:
        raise MimiiDueSourceError(
            f"unsupported MIMII DUE prepared-source directory: {directory_name!r}"
        )

    if split != expected_split:
        raise MimiiDueSourceError(
            f"MIMII DUE filename split does not match directory for {path}: "
            f"expected {expected_split!r}, got {split!r}"
        )
    if expected_domain is not None and domain != expected_domain:
        raise MimiiDueSourceError(
            f"MIMII DUE filename domain does not match directory for {path}: "
            f"expected {expected_domain!r}, got {domain!r}"
        )
    if split == "test" and raw_attribute is not None:
        raise MimiiDueSourceError(
            f"MIMII DUE test filename must not contain operating attributes: {path.name!r}"
        )

    return _MimiiDueClip(
        path=path,
        group=group,
        machine=machine,
        section=section,
        domain=domain,
        split=split,
        label=label,
        clip_number=clip_number,
        raw_attribute=raw_attribute,
    )


def _validation_clips(
    clips: tuple[_MimiiDueClip, ...],
    *,
    full: bool,
) -> tuple[_MimiiDueClip, ...]:
    if full:
        return clips

    by_stratum: dict[
        tuple[str, str, str, str, str],
        list[_MimiiDueClip],
    ] = defaultdict(list)
    for clip in clips:
        key = (clip.group, clip.machine, clip.domain, clip.split, clip.label)
        by_stratum[key].append(clip)

    selected: list[_MimiiDueClip] = []
    for key in sorted(by_stratum):
        values = by_stratum[key]
        positions = sorted({0, len(values) // 2, len(values) - 1})
        selected.extend(values[position] for position in positions)
    return tuple(selected)


def _read_wav_values(path: Path) -> tuple[tuple[float], ...]:
    try:
        with wave.open(str(path), "rb") as source:
            _validate_open_wav_header(source, path)
            payload = source.readframes(_FRAMES_PER_CLIP)
    except (EOFError, OSError, wave.Error) as error:
        raise MimiiDueSourceError(f"failed to read MIMII DUE WAV {path}: {error}") from error

    expected_bytes = _FRAMES_PER_CLIP * (_SAMPLE_WIDTH_BITS // 8)
    if len(payload) != expected_bytes:
        raise MimiiDueSourceError(
            f"truncated MIMII DUE WAV payload for {path}: "
            f"expected {expected_bytes} bytes, got {len(payload)}"
        )

    return tuple((float(sample),) for (sample,) in struct.iter_unpack("<h", payload))


def _validate_wav_header(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as source:
            _validate_open_wav_header(source, path)
    except (EOFError, OSError, wave.Error) as error:
        raise MimiiDueSourceError(f"failed to read MIMII DUE WAV header {path}: {error}") from error


def _validate_open_wav_header(source: wave.Wave_read, path: Path) -> None:
    channels = source.getnchannels()
    sample_width_bits = source.getsampwidth() * 8
    sampling_rate_hz = float(source.getframerate())
    frame_count = source.getnframes()
    compression = source.getcomptype()

    observed = (
        channels,
        sample_width_bits,
        sampling_rate_hz,
        frame_count,
        compression,
    )
    expected = (
        _CHANNEL_COUNT,
        _SAMPLE_WIDTH_BITS,
        _SAMPLING_RATE_HZ,
        _FRAMES_PER_CLIP,
        "NONE",
    )
    if observed != expected:
        raise MimiiDueSourceError(
            "unexpected MIMII DUE WAV profile for "
            f"{path}: expected channels={_CHANNEL_COUNT}, "
            f"sample_width_bits={_SAMPLE_WIDTH_BITS}, "
            f"sampling_rate_hz={_SAMPLING_RATE_HZ:g}, "
            f"frames={_FRAMES_PER_CLIP}, compression='NONE'; "
            f"got channels={channels}, sample_width_bits={sample_width_bits}, "
            f"sampling_rate_hz={sampling_rate_hz:g}, frames={frame_count}, "
            f"compression={compression!r}"
        )


def _profile_issues(
    source: Path,
    observed_counts: Counter[tuple[str, str, str, str, str]],
) -> tuple[str, ...]:
    issues = list(_structure_issues(source))

    for key in sorted(_EXPECTED_COUNTS):
        expected = _EXPECTED_COUNTS[key]
        found = observed_counts.get(key, 0)
        if found != expected:
            group, machine, domain, split, label = key
            issues.append(
                "clip count mismatch: "
                f"{group}/{machine}/{domain}/{split}/{label}: "
                f"expected {expected}, found {found}"
            )

    for key in sorted(set(observed_counts) - set(_EXPECTED_COUNTS)):
        group, machine, domain, split, label = key
        issues.append(
            "unexpected clip population: "
            f"{group}/{machine}/{domain}/{split}/{label}: "
            f"found {observed_counts[key]}"
        )
    return tuple(issues)


def _structure_issues(source: Path) -> tuple[str, ...]:
    issues: list[str] = []

    expected_groups = set(_GROUP_DIRECTORIES)
    observed_groups = {path.name for path in source.iterdir() if not path.name.startswith(".")}
    for name in sorted(observed_groups - expected_groups):
        issues.append(f"unexpected top-level entry: {name}")
    for name in sorted(expected_groups - observed_groups):
        issues.append(f"missing group directory: {name}")

    for group, directory_names in _GROUP_DIRECTORIES.items():
        group_dir = source / group
        if not group_dir.is_dir():
            continue

        observed_machines = {
            path.name for path in group_dir.iterdir() if not path.name.startswith(".")
        }
        expected_machines = set(_MACHINE_TYPES)
        for name in sorted(observed_machines - expected_machines):
            issues.append(f"unexpected machine entry: {group}/{name}")
        for name in sorted(expected_machines - observed_machines):
            issues.append(f"missing machine directory: {group}/{name}")

        for machine in _MACHINE_TYPES:
            machine_dir = group_dir / machine
            if not machine_dir.is_dir():
                continue

            observed_directories = {
                path.name for path in machine_dir.iterdir() if not path.name.startswith(".")
            }
            expected_directories = set(directory_names)
            for name in sorted(observed_directories - expected_directories):
                issues.append(f"unexpected split entry: {group}/{machine}/{name}")
            for name in sorted(expected_directories - observed_directories):
                issues.append(f"missing split directory: {group}/{machine}/{name}")

    return tuple(issues)
