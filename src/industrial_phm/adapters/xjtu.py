"""XJTU-SY bearing dataset adapter."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from industrial_phm.contracts import CanonicalTimeSeries

_DATASET_ID = "xjtu-sy"
_EXPECTED_HEADER = (
    "Horizontal_vibration_signals",
    "Vertical_vibration_signals",
)
_EXPECTED_SAMPLE_COUNT = 32_768
_SAMPLING_RATE_HZ = 25_600.0
_ACQUISITION_PERIOD_SECONDS = 60.0
_CONDITION_PATTERN = re.compile(r"^(?P<speed_hz>\d+(?:\.\d+)?)Hz(?P<load_kn>\d+(?:\.\d+)?)kN$")
_BEARING_PATTERN = re.compile(r"^Bearing(?P<group>\d+)_(?P<index>\d+)$")
_EXPECTED_RUN_ACQUISITIONS = {
    ("35Hz12kN", "Bearing1_1"): 123,
    ("35Hz12kN", "Bearing1_2"): 161,
    ("35Hz12kN", "Bearing1_3"): 158,
    ("35Hz12kN", "Bearing1_4"): 122,
    ("35Hz12kN", "Bearing1_5"): 52,
    ("37.5Hz11kN", "Bearing2_1"): 491,
    ("37.5Hz11kN", "Bearing2_2"): 161,
    ("37.5Hz11kN", "Bearing2_3"): 533,
    ("37.5Hz11kN", "Bearing2_4"): 42,
    ("37.5Hz11kN", "Bearing2_5"): 339,
    ("40Hz10kN", "Bearing3_1"): 2_538,
    ("40Hz10kN", "Bearing3_2"): 2_496,
    ("40Hz10kN", "Bearing3_3"): 371,
    ("40Hz10kN", "Bearing3_4"): 1_515,
    ("40Hz10kN", "Bearing3_5"): 114,
}


class XjtuSySourceError(ValueError):
    """Raised when a local XJTU-SY source violates the observed dataset structure."""


@dataclass(frozen=True, slots=True)
class XjtuSyValidationReport:
    """Dataset-specific compatibility summary for an extracted XJTU-SY source."""

    source: Path
    full: bool
    operating_condition_count: int
    bearing_run_count: int
    acquisition_count: int
    checked_acquisition_count: int
    channels: tuple[str, ...]
    samples_per_acquisition: int
    sampling_rate_hz: float
    profile_issues: tuple[str, ...]

    @property
    def profile_matches(self) -> bool:
        """Return whether the source matches the observed complete XJTU-SY profile."""
        return not self.profile_issues


@dataclass(frozen=True, slots=True)
class _XjtuRun:
    condition_name: str
    speed_hz: float
    load_kn: float
    bearing_dir: Path
    acquisitions: tuple[tuple[int, Path], ...]


class XjtuSyAdapter:
    """Yield one canonical waveform segment for each XJTU-SY acquisition CSV."""

    @property
    def domain(self) -> str:
        """Return the stable dataset/domain identifier."""
        return _DATASET_ID

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        """Read the extracted XJTU-SY dataset root lazily, one acquisition at a time."""
        for run in _iter_runs(source):
            for acquisition_index, path in run.acquisitions:
                yield _read_acquisition(
                    source_root=source,
                    condition_name=run.condition_name,
                    speed_hz=run.speed_hz,
                    load_kn=run.load_kn,
                    bearing_dir=run.bearing_dir,
                    acquisition_index=acquisition_index,
                    path=path,
                )


def validate_xjtu_source(source: Path, *, full: bool = False) -> XjtuSyValidationReport:
    """Validate local XJTU-SY structure and representative or complete waveform content.

    This is a compatibility check against the observed official-mirror profile. It does
    not prove upstream authenticity because the XJTU-SY manifest has no pinned checksum.
    """
    runs = tuple(_iter_runs(source))
    observed = {
        (run.condition_name, run.bearing_dir.name): len(run.acquisitions) for run in runs
    }

    checked_acquisition_count = 0
    for run in runs:
        for acquisition_index, path in _validation_acquisitions(run.acquisitions, full=full):
            _read_acquisition(
                source_root=source,
                condition_name=run.condition_name,
                speed_hz=run.speed_hz,
                load_kn=run.load_kn,
                bearing_dir=run.bearing_dir,
                acquisition_index=acquisition_index,
                path=path,
            )
            checked_acquisition_count += 1

    return XjtuSyValidationReport(
        source=source,
        full=full,
        operating_condition_count=len({run.condition_name for run in runs}),
        bearing_run_count=len(runs),
        acquisition_count=sum(len(run.acquisitions) for run in runs),
        checked_acquisition_count=checked_acquisition_count,
        channels=_EXPECTED_HEADER,
        samples_per_acquisition=_EXPECTED_SAMPLE_COUNT,
        sampling_rate_hz=_SAMPLING_RATE_HZ,
        profile_issues=_profile_issues(observed),
    )


def _iter_runs(source: Path) -> Iterable[_XjtuRun]:
    if not source.is_dir():
        raise XjtuSySourceError(f"XJTU-SY source directory does not exist: {source}")

    condition_dirs = [
        path for path in source.iterdir() if path.is_dir() and not path.name.startswith(".")
    ]
    if not condition_dirs:
        raise XjtuSySourceError(
            f"XJTU-SY source contains no operating-condition directories: {source}"
        )

    for condition_dir in sorted(condition_dirs, key=_condition_sort_key):
        speed_hz, load_kn = _parse_condition_name(condition_dir.name)
        bearing_dirs = [
            path
            for path in condition_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        if not bearing_dirs:
            raise XjtuSySourceError(
                f"XJTU-SY operating condition contains no bearing runs: {condition_dir}"
            )

        for bearing_dir in sorted(bearing_dirs, key=_bearing_sort_key):
            _parse_bearing_name(bearing_dir.name)
            yield _XjtuRun(
                condition_name=condition_dir.name,
                speed_hz=speed_hz,
                load_kn=load_kn,
                bearing_dir=bearing_dir,
                acquisitions=tuple(_acquisition_files(bearing_dir)),
            )


def _validation_acquisitions(
    acquisitions: tuple[tuple[int, Path], ...],
    *,
    full: bool,
) -> tuple[tuple[int, Path], ...]:
    if full:
        return acquisitions

    positions = sorted({0, len(acquisitions) // 2, len(acquisitions) - 1})
    return tuple(acquisitions[position] for position in positions)


def _profile_issues(observed: dict[tuple[str, str], int]) -> tuple[str, ...]:
    expected_keys = set(_EXPECTED_RUN_ACQUISITIONS)
    observed_keys = set(observed)
    issues: list[str] = []

    for condition_name, bearing_name in sorted(expected_keys - observed_keys):
        expected = _EXPECTED_RUN_ACQUISITIONS[(condition_name, bearing_name)]
        issues.append(
            f"missing run: {condition_name}/{bearing_name} (expected {expected} acquisitions)"
        )

    for condition_name, bearing_name in sorted(observed_keys - expected_keys):
        found = observed[(condition_name, bearing_name)]
        issues.append(
            f"unexpected run: {condition_name}/{bearing_name} (found {found} acquisitions)"
        )

    for condition_name, bearing_name in sorted(expected_keys & observed_keys):
        key = (condition_name, bearing_name)
        expected = _EXPECTED_RUN_ACQUISITIONS[key]
        found = observed[key]
        if found != expected:
            issues.append(
                f"acquisition count mismatch: {condition_name}/{bearing_name}: "
                f"expected {expected}, found {found}"
            )

    return tuple(issues)


def _parse_condition_name(name: str) -> tuple[float, float]:
    match = _CONDITION_PATTERN.fullmatch(name)
    if match is None:
        raise XjtuSySourceError(f"unexpected XJTU-SY operating-condition directory name: {name!r}")
    return float(match.group("speed_hz")), float(match.group("load_kn"))


def _condition_sort_key(path: Path) -> tuple[float, float, str]:
    speed_hz, load_kn = _parse_condition_name(path.name)
    return speed_hz, load_kn, path.name


def _parse_bearing_name(name: str) -> tuple[int, int]:
    match = _BEARING_PATTERN.fullmatch(name)
    if match is None:
        raise XjtuSySourceError(f"unexpected XJTU-SY bearing directory name: {name!r}")
    return int(match.group("group")), int(match.group("index"))


def _bearing_sort_key(path: Path) -> tuple[int, int, str]:
    group, index = _parse_bearing_name(path.name)
    return group, index, path.name


def _acquisition_files(bearing_dir: Path) -> list[tuple[int, Path]]:
    csv_paths = sorted(bearing_dir.glob("*.csv"), key=lambda path: path.name)
    if not csv_paths:
        raise XjtuSySourceError(f"XJTU-SY bearing run contains no CSV acquisitions: {bearing_dir}")

    indexed: list[tuple[int, Path]] = []
    for path in csv_paths:
        try:
            acquisition_index = int(path.stem)
        except ValueError as error:
            raise XjtuSySourceError(
                f"XJTU-SY acquisition filename must be a positive integer: {path.name!r}"
            ) from error
        if acquisition_index <= 0:
            raise XjtuSySourceError(
                f"XJTU-SY acquisition filename must be a positive integer: {path.name!r}"
            )
        indexed.append((acquisition_index, path))

    indexed.sort(key=lambda item: item[0])
    observed = [index for index, _ in indexed]
    expected = list(range(1, len(indexed) + 1))
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        unexpected = sorted(set(observed) - set(expected))
        raise XjtuSySourceError(
            "XJTU-SY acquisition filenames must form a contiguous 1..N lifecycle sequence "
            f"for {bearing_dir}; missing={missing[:10]}, unexpected={unexpected[:10]}"
        )

    return indexed


def _read_acquisition(
    *,
    source_root: Path,
    condition_name: str,
    speed_hz: float,
    load_kn: float,
    bearing_dir: Path,
    acquisition_index: int,
    path: Path,
) -> CanonicalTimeSeries:
    values: list[tuple[float, float]] = []

    try:
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.reader(source)
            try:
                header = tuple(next(reader))
            except StopIteration as error:
                raise XjtuSySourceError(f"XJTU-SY acquisition CSV is empty: {path}") from error

            if header != _EXPECTED_HEADER:
                raise XjtuSySourceError(
                    "unexpected XJTU-SY CSV header for "
                    f"{path}: expected {_EXPECTED_HEADER}, got {header}"
                )

            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(_EXPECTED_HEADER):
                    raise XjtuSySourceError(
                        f"unexpected XJTU-SY CSV width at {path}:{line_number}: {len(row)}"
                    )
                try:
                    values.append((float(row[0]), float(row[1])))
                except ValueError as error:
                    raise XjtuSySourceError(
                        f"non-numeric XJTU-SY vibration value at {path}:{line_number}"
                    ) from error
    except OSError as error:
        raise XjtuSySourceError(
            f"failed to read XJTU-SY acquisition CSV {path}: {error}"
        ) from error

    if len(values) != _EXPECTED_SAMPLE_COUNT:
        raise XjtuSySourceError(
            f"unexpected XJTU-SY sample count for {path}: "
            f"expected {_EXPECTED_SAMPLE_COUNT}, got {len(values)}"
        )

    return CanonicalTimeSeries(
        asset_id=bearing_dir.name,
        timestamps=None,
        channels=_EXPECTED_HEADER,
        values=values,
        sampling_rate_hz=_SAMPLING_RATE_HZ,
        metadata={
            "dataset_id": _DATASET_ID,
            "operating_condition": condition_name,
            "rotational_speed_hz": speed_hz,
            "radial_load_kn": load_kn,
            "acquisition_index": acquisition_index,
            "acquisition_period_seconds": _ACQUISITION_PERIOD_SECONDS,
            "source_file": path.relative_to(source_root).as_posix(),
        },
    )
