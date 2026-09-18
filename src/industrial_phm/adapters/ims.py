"""IMS Bearing Data Set adapter and local-source validation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from industrial_phm.contracts import CanonicalTimeSeries

_DATASET_ID = "ims-bearings"
_SAMPLES_PER_ACQUISITION = 20_480
_SAMPLING_RATE_HZ = 20_000.0
_TIMESTAMP_FORMAT = "%Y.%m.%d.%H.%M.%S"


class ImsBearingSourceError(ValueError):
    """Raised when a prepared IMS source violates the observed archive structure."""


@dataclass(frozen=True, slots=True)
class ImsBearingTestSummary:
    """Observed structure for one IMS run-to-failure test."""

    test_id: str
    source_directory: str
    archive_member: str
    acquisition_count: int
    checked_acquisition_count: int
    channel_count: int
    first_acquisition_at: datetime
    last_acquisition_at: datetime
    readme_acquisition_count: int

    @property
    def archive_extension_acquisition_count(self) -> int:
        """Return acquisitions in the archive extension beyond the README scope."""
        return max(0, self.acquisition_count - self.readme_acquisition_count)


@dataclass(frozen=True, slots=True)
class ImsBearingValidationReport:
    """Dataset-specific compatibility summary for an extracted IMS source."""

    source: Path
    full: bool
    tests: tuple[ImsBearingTestSummary, ...]
    acquisition_count: int
    checked_acquisition_count: int
    samples_per_acquisition: int
    sampling_rate_hz: float
    profile_issues: tuple[str, ...]

    @property
    def profile_matches(self) -> bool:
        """Return whether the source matches the locally observed official archive."""
        return not self.profile_issues


@dataclass(frozen=True, slots=True)
class _ImsTestProfile:
    test_id: str
    relative_directory: Path
    archive_member: str
    expected_acquisition_count: int
    readme_acquisition_count: int
    readme_last_acquisition_at: datetime
    expected_first_acquisition_at: datetime
    expected_last_acquisition_at: datetime
    bearing_channels: tuple[tuple[str, ...], ...]

    @property
    def channel_count(self) -> int:
        return sum(len(channels) for channels in self.bearing_channels)


@dataclass(frozen=True, slots=True)
class _ImsAcquisition:
    timestamp: datetime
    path: Path


_TEST_PROFILES = (
    _ImsTestProfile(
        test_id="set-1",
        relative_directory=Path("1st_test"),
        archive_member="1st_test.rar",
        expected_acquisition_count=2_156,
        readme_acquisition_count=2_156,
        readme_last_acquisition_at=datetime(2003, 11, 25, 23, 39, 56),
        expected_first_acquisition_at=datetime(2003, 10, 22, 12, 6, 24),
        expected_last_acquisition_at=datetime(2003, 11, 25, 23, 39, 56),
        bearing_channels=(
            ("x_axis_vibration", "y_axis_vibration"),
            ("x_axis_vibration", "y_axis_vibration"),
            ("x_axis_vibration", "y_axis_vibration"),
            ("x_axis_vibration", "y_axis_vibration"),
        ),
    ),
    _ImsTestProfile(
        test_id="set-2",
        relative_directory=Path("2nd_test"),
        archive_member="2nd_test.rar",
        expected_acquisition_count=984,
        readme_acquisition_count=984,
        readme_last_acquisition_at=datetime(2004, 2, 19, 6, 22, 39),
        expected_first_acquisition_at=datetime(2004, 2, 12, 10, 32, 39),
        expected_last_acquisition_at=datetime(2004, 2, 19, 6, 22, 39),
        bearing_channels=(("vibration",),) * 4,
    ),
    _ImsTestProfile(
        test_id="set-3",
        relative_directory=Path("4th_test") / "txt",
        archive_member="3rd_test.rar",
        expected_acquisition_count=6_324,
        readme_acquisition_count=4_448,
        readme_last_acquisition_at=datetime(2004, 4, 4, 19, 1, 57),
        expected_first_acquisition_at=datetime(2004, 3, 4, 9, 27, 46),
        expected_last_acquisition_at=datetime(2004, 4, 18, 2, 42, 55),
        bearing_channels=(("vibration",),) * 4,
    ),
)


class ImsBearingAdapter:
    """Yield one canonical waveform segment per bearing and IMS acquisition file."""

    @property
    def domain(self) -> str:
        """Return the stable dataset/domain identifier."""
        return _DATASET_ID

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        """Read a prepared IMS source lazily in test, timestamp, and bearing order."""
        observed = _observed_tests(source)
        if not observed:
            message = "IMS source contains no recognized test directories: " + str(source)
            raise ImsBearingSourceError(message)

        for profile, acquisitions in observed:
            for acquisition_index, acquisition in enumerate(acquisitions, start=1):
                values = _read_waveform(acquisition.path, profile.channel_count)
                yield from _canonical_series(
                    source=source,
                    profile=profile,
                    acquisition=acquisition,
                    acquisition_index=acquisition_index,
                    values=values,
                )

    def iter_test_series(
        self,
        source: Path,
        test_id: str,
        *,
        archive_scope: Literal["all", "readme-documented"] = "all",
    ) -> Iterable[CanonicalTimeSeries]:
        """Read one IMS test without materializing excluded tests or archive-extension payloads."""
        profile = _test_profile(test_id)
        directory = source / profile.relative_directory
        if not directory.is_dir():
            raise ImsBearingSourceError(
                f"IMS source is missing {test_id!r}: {profile.relative_directory.as_posix()}"
            )
        acquisitions = _scope_acquisitions(
            profile,
            _acquisition_files(directory),
            archive_scope=archive_scope,
        )
        for acquisition_index, acquisition in enumerate(acquisitions, start=1):
            values = _read_waveform(acquisition.path, profile.channel_count)
            yield from _canonical_series(
                source=source,
                profile=profile,
                acquisition=acquisition,
                acquisition_index=acquisition_index,
                values=values,
            )


def validate_ims_source(source: Path, *, full: bool = False) -> ImsBearingValidationReport:
    """Validate a prepared IMS source against the locally observed official archive profile."""
    observed = _observed_tests(source)
    if not observed:
        message = "IMS source contains no recognized test directories: " + str(source)
        raise ImsBearingSourceError(message)

    summaries: list[ImsBearingTestSummary] = []
    checked_acquisition_count = 0
    for profile, acquisitions in observed:
        selected = _validation_acquisitions(acquisitions, full=full)
        for acquisition in selected:
            _read_waveform(acquisition.path, profile.channel_count)
        checked_acquisition_count += len(selected)
        summaries.append(
            ImsBearingTestSummary(
                test_id=profile.test_id,
                source_directory=profile.relative_directory.as_posix(),
                archive_member=profile.archive_member,
                acquisition_count=len(acquisitions),
                checked_acquisition_count=len(selected),
                channel_count=profile.channel_count,
                first_acquisition_at=acquisitions[0].timestamp,
                last_acquisition_at=acquisitions[-1].timestamp,
                readme_acquisition_count=profile.readme_acquisition_count,
            )
        )

    return ImsBearingValidationReport(
        source=source,
        full=full,
        tests=tuple(summaries),
        acquisition_count=sum(summary.acquisition_count for summary in summaries),
        checked_acquisition_count=checked_acquisition_count,
        samples_per_acquisition=_SAMPLES_PER_ACQUISITION,
        sampling_rate_hz=_SAMPLING_RATE_HZ,
        profile_issues=_profile_issues(source, observed),
    )


def _test_profile(test_id: str) -> _ImsTestProfile:
    profile = next((item for item in _TEST_PROFILES if item.test_id == test_id), None)
    if profile is None:
        raise ImsBearingSourceError(f"unknown IMS test_id: {test_id!r}")
    return profile


def _scope_acquisitions(
    profile: _ImsTestProfile,
    acquisitions: tuple[_ImsAcquisition, ...],
    *,
    archive_scope: Literal["all", "readme-documented"],
) -> tuple[_ImsAcquisition, ...]:
    if archive_scope == "all":
        return acquisitions
    if archive_scope == "readme-documented":
        selected = tuple(
            acquisition
            for acquisition in acquisitions
            if acquisition.timestamp <= profile.readme_last_acquisition_at
        )
        if not selected:
            raise ImsBearingSourceError(
                f"IMS {profile.test_id} README-documented scope contains no acquisitions"
            )
        return selected
    raise ImsBearingSourceError(f"unsupported IMS archive_scope: {archive_scope!r}")


def _observed_tests(
    source: Path,
) -> tuple[tuple[_ImsTestProfile, tuple[_ImsAcquisition, ...]], ...]:
    if not source.is_dir():
        raise ImsBearingSourceError(f"IMS source directory does not exist: {source}")

    observed: list[tuple[_ImsTestProfile, tuple[_ImsAcquisition, ...]]] = []
    for profile in _TEST_PROFILES:
        directory = source / profile.relative_directory
        if directory.is_dir():
            observed.append((profile, _acquisition_files(directory)))
    return tuple(observed)


def _acquisition_files(directory: Path) -> tuple[_ImsAcquisition, ...]:
    paths = tuple(path for path in directory.iterdir() if _is_visible_file(path))
    if not paths:
        raise ImsBearingSourceError(f"IMS test directory contains no acquisitions: {directory}")

    acquisitions: list[_ImsAcquisition] = []
    for path in paths:
        try:
            timestamp = datetime.strptime(path.name, _TIMESTAMP_FORMAT)
        except ValueError as error:
            raise ImsBearingSourceError(
                f"IMS acquisition filename must match {_TIMESTAMP_FORMAT!r}: {path.name!r}"
            ) from error
        acquisitions.append(_ImsAcquisition(timestamp=timestamp, path=path))

    acquisitions.sort(key=lambda acquisition: acquisition.timestamp)
    timestamps = tuple(acquisition.timestamp for acquisition in acquisitions)
    if len(timestamps) != len(set(timestamps)):
        raise ImsBearingSourceError(f"IMS acquisition timestamps must be unique: {directory}")
    return tuple(acquisitions)


def _is_visible_file(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(".")


def _validation_acquisitions(
    acquisitions: tuple[_ImsAcquisition, ...],
    *,
    full: bool,
) -> tuple[_ImsAcquisition, ...]:
    if full:
        return acquisitions
    positions = sorted({0, len(acquisitions) // 2, len(acquisitions) - 1})
    return tuple(acquisitions[position] for position in positions)


def _profile_issues(
    source: Path,
    observed: tuple[tuple[_ImsTestProfile, tuple[_ImsAcquisition, ...]], ...],
) -> tuple[str, ...]:
    by_test_id = {profile.test_id: (profile, acquisitions) for profile, acquisitions in observed}
    issues: list[str] = []

    for profile in _TEST_PROFILES:
        item = by_test_id.get(profile.test_id)
        if item is None:
            issues.append(
                f"missing test: {profile.relative_directory.as_posix()} "
                f"(expected {profile.expected_acquisition_count} acquisitions)"
            )
            continue

        _, acquisitions = item
        if len(acquisitions) != profile.expected_acquisition_count:
            issues.append(
                f"acquisition count mismatch: {profile.test_id}: "
                f"expected {profile.expected_acquisition_count}, found {len(acquisitions)}"
            )
        if acquisitions[0].timestamp != profile.expected_first_acquisition_at:
            issues.append(
                f"first acquisition mismatch: {profile.test_id}: "
                f"expected {profile.expected_first_acquisition_at.isoformat()}, "
                f"found {acquisitions[0].timestamp.isoformat()}"
            )
        if acquisitions[-1].timestamp != profile.expected_last_acquisition_at:
            issues.append(
                f"last acquisition mismatch: {profile.test_id}: "
                f"expected {profile.expected_last_acquisition_at.isoformat()}, "
                f"found {acquisitions[-1].timestamp.isoformat()}"
            )

    expected_top_level = {profile.relative_directory.parts[0] for profile in _TEST_PROFILES}
    observed_top_level = {path.name for path in source.iterdir() if not path.name.startswith(".")}
    for name in sorted(observed_top_level - expected_top_level):
        issues.append(f"unexpected top-level entry: {name}")
    return tuple(issues)


def _read_waveform(path: Path, channel_count: int) -> tuple[tuple[float, ...], ...]:
    values: list[tuple[float, ...]] = []
    try:
        with path.open(encoding="ascii") as source:
            for line_number, line in enumerate(source, start=1):
                fields = line.split()
                if len(fields) != channel_count:
                    raise ImsBearingSourceError(
                        f"unexpected IMS waveform width at {path}:{line_number}: "
                        f"expected {channel_count}, got {len(fields)}"
                    )
                try:
                    values.append(tuple(float(value) for value in fields))
                except ValueError as error:
                    raise ImsBearingSourceError(
                        f"non-numeric IMS waveform value at {path}:{line_number}"
                    ) from error
    except (OSError, UnicodeError) as error:
        raise ImsBearingSourceError(f"failed to read IMS waveform {path}: {error}") from error

    if len(values) != _SAMPLES_PER_ACQUISITION:
        raise ImsBearingSourceError(
            f"unexpected IMS sample count for {path}: "
            f"expected {_SAMPLES_PER_ACQUISITION}, got {len(values)}"
        )
    return tuple(values)


def _canonical_series(
    *,
    source: Path,
    profile: _ImsTestProfile,
    acquisition: _ImsAcquisition,
    acquisition_index: int,
    values: tuple[tuple[float, ...], ...],
) -> Iterable[CanonicalTimeSeries]:
    channel_offset = 0
    archive_scope = (
        "readme-documented"
        if acquisition.timestamp <= profile.readme_last_acquisition_at
        else "archive-extension"
    )
    for bearing_number, channels in enumerate(profile.bearing_channels, start=1):
        next_offset = channel_offset + len(channels)
        bearing_values = tuple(row[channel_offset:next_offset] for row in values)
        yield CanonicalTimeSeries(
            asset_id=f"{profile.test_id}-bearing-{bearing_number}",
            timestamps=None,
            channels=channels,
            values=bearing_values,
            sampling_rate_hz=_SAMPLING_RATE_HZ,
            metadata={
                "dataset_id": _DATASET_ID,
                "test_id": profile.test_id,
                "bearing_number": bearing_number,
                "acquisition_index": acquisition_index,
                "acquisition_timestamp": acquisition.timestamp.isoformat(),
                "acquisition_time_basis": "filename-local-clock",
                "archive_scope": archive_scope,
                "rotational_speed_rpm": 2_000.0,
                "radial_load_lb": 6_000.0,
                "source_archive_member": profile.archive_member,
                "source_file": acquisition.path.relative_to(source).as_posix(),
            },
        )
        channel_offset = next_offset
