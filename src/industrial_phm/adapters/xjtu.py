"""XJTU-SY bearing dataset adapter."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
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


class XjtuSySourceError(ValueError):
    """Raised when a local XJTU-SY source violates the observed dataset structure."""


class XjtuSyAdapter:
    """Yield one canonical waveform segment for each XJTU-SY acquisition CSV."""

    @property
    def domain(self) -> str:
        """Return the stable dataset/domain identifier."""
        return _DATASET_ID

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        """Read the extracted XJTU-SY dataset root lazily, one acquisition at a time."""
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
                for acquisition_index, path in _acquisition_files(bearing_dir):
                    yield _read_acquisition(
                        source_root=source,
                        condition_name=condition_dir.name,
                        speed_hz=speed_hz,
                        load_kn=load_kn,
                        bearing_dir=bearing_dir,
                        acquisition_index=acquisition_index,
                        path=path,
                    )


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
