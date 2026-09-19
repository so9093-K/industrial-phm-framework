"""Deterministic clip-level audio representation for the MIMII DUE v1 protocol."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType

import numpy as np

from industrial_phm.contracts import CanonicalTimeSeries

AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID = "audio-logmel-statistical-v1"

_SAMPLE_RATE_HZ = 16_000.0
_SAMPLE_COUNT = 160_000
_FRAME_LENGTH = 1_024
_HOP_LENGTH = 512
_FFT_SIZE = 1_024
_MEL_BAND_COUNT = 64
_LOG_FLOOR = 1e-12
_PCM_DIVISOR = 32_768.0
_EXPECTED_CHANNELS = ("pcm_amplitude",)
_EXPECTED_FRAME_COUNT = 311
_MetadataValue = str | int | float | bool | None
_FlatValue = str | int | float | bool | None


class AudioFeatureError(ValueError):
    """Raised when canonical audio cannot produce the protocol-defined representation."""


@dataclass(frozen=True, slots=True)
class AudioLogMelRepresentationSpec:
    """Stable numerical parameters needed to reproduce audio-logmel-statistical-v1."""

    sample_rate_hz: float = _SAMPLE_RATE_HZ
    sample_count: int = _SAMPLE_COUNT
    pcm_full_scale_divisor: float = _PCM_DIVISOR
    frame_length_samples: int = _FRAME_LENGTH
    hop_length_samples: int = _HOP_LENGTH
    window: str = "symmetric-hann"
    centering: bool = False
    padding: str = "none"
    fft_size: int = _FFT_SIZE
    power_normalization: str = "abs-rfft-squared-divide-window-power"
    mel_scale: str = "htk"
    mel_band_count: int = _MEL_BAND_COUNT
    minimum_frequency_hz: float = 0.0
    maximum_frequency_hz: float = _SAMPLE_RATE_HZ / 2.0
    mel_filter_normalization: str = "triangular-peak-one-no-area-normalization"
    log_floor: float = _LOG_FLOOR
    frame_count: int = _EXPECTED_FRAME_COUNT
    feature_count: int = _MEL_BAND_COUNT * 2
    clip_aggregation: str = "per-band-frame-mean-population-std-interleaved"


@dataclass(frozen=True, slots=True)
class AudioFeatureVector:
    """Immutable clip-level audio feature vector with source provenance."""

    feature_set_id: str
    asset_id: str
    feature_names: Sequence[str]
    values: Sequence[float]
    metadata: Mapping[str, _MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        feature_names = tuple(self.feature_names)
        values = tuple(float(value) for value in self.values)
        metadata = MappingProxyType(dict(self.metadata))

        if not self.feature_set_id.strip():
            raise ValueError("feature_set_id must not be empty")
        if not self.asset_id.strip():
            raise ValueError("asset_id must not be empty")
        if not feature_names:
            raise ValueError("feature_names must contain at least one feature")
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("feature_names must be unique")
        if len(feature_names) != len(values):
            raise ValueError("feature_names and values must have the same length")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("feature values must be finite")

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "metadata", metadata)

    def to_flat_record(self) -> dict[str, _FlatValue]:
        """Return a table-friendly record while preserving clip metadata as provenance."""
        record: dict[str, _FlatValue] = {
            "feature_set_id": self.feature_set_id,
            "asset_id": self.asset_id,
        }
        record.update((f"meta.{key}", value) for key, value in self.metadata.items())
        record.update(zip(self.feature_names, self.values, strict=True))
        return record


def extract_audio_logmel_features(series: CanonicalTimeSeries) -> AudioFeatureVector:
    """Extract the fixed 128-value log-mel statistical representation from one clip."""
    _validate_audio_series(series)

    pcm_values = np.fromiter(
        (row[0] for row in series.values),
        dtype=np.float64,
        count=_SAMPLE_COUNT,
    )
    if not bool(np.all(np.isfinite(pcm_values))):
        raise AudioFeatureError("audio PCM amplitude contains non-finite values")
    if bool(np.any((pcm_values < -32_768.0) | (pcm_values > 32_767.0))):
        raise AudioFeatureError("audio PCM amplitude must stay within signed 16-bit range")
    if not bool(np.all(pcm_values == np.trunc(pcm_values))):
        raise AudioFeatureError("audio PCM amplitude must contain integer-valued PCM samples")

    samples = pcm_values / _PCM_DIVISOR
    window = 0.5 - 0.5 * np.cos(
        2.0 * np.pi * np.arange(_FRAME_LENGTH, dtype=np.float64) / (_FRAME_LENGTH - 1)
    )
    frames = np.lib.stride_tricks.sliding_window_view(samples, _FRAME_LENGTH)[::_HOP_LENGTH]
    if frames.shape != (_EXPECTED_FRAME_COUNT, _FRAME_LENGTH):
        raise AudioFeatureError(
            f"audio-logmel-statistical-v1 requires exactly {_EXPECTED_FRAME_COUNT} complete frames"
        )

    spectrum = np.fft.rfft(frames * window, n=_FFT_SIZE, axis=1)
    window_power = float(np.sum(window * window))
    power = (np.abs(spectrum) ** 2) / window_power

    mel_filterbank = np.asarray(_mel_filterbank(), dtype=np.float64)
    mel_energy = power @ mel_filterbank.T
    log_energy = np.log(np.maximum(mel_energy, _LOG_FLOOR))

    means = np.mean(log_energy, axis=0)
    standard_deviations = np.std(log_energy, axis=0, ddof=0)
    feature_values = np.empty(_MEL_BAND_COUNT * 2, dtype=np.float64)
    feature_values[0::2] = means
    feature_values[1::2] = standard_deviations

    values = tuple(float(value) for value in feature_values)
    if not all(math.isfinite(value) for value in values):
        raise AudioFeatureError("audio representation produced non-finite feature values")

    return AudioFeatureVector(
        feature_set_id=AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
        asset_id=series.asset_id,
        feature_names=audio_logmel_feature_names(),
        values=values,
        metadata=series.metadata,
    )


def iter_audio_logmel_features(
    series_iterable: Iterable[CanonicalTimeSeries],
) -> Iterator[AudioFeatureVector]:
    """Transform audio clips lazily so dataset waveforms are not materialized together."""
    for series in series_iterable:
        yield extract_audio_logmel_features(series)


def audio_logmel_representation_spec() -> AudioLogMelRepresentationSpec:
    """Return the immutable protocol-defined representation parameters."""
    return AudioLogMelRepresentationSpec()


def audio_logmel_feature_names() -> tuple[str, ...]:
    """Return the stable interleaved mean/std feature schema for 64 mel bands."""
    return tuple(
        f"feature.logmel.band_{band:02d}.{statistic}"
        for band in range(_MEL_BAND_COUNT)
        for statistic in ("mean", "std")
    )


def _validate_audio_series(series: CanonicalTimeSeries) -> None:
    if tuple(series.channels) != _EXPECTED_CHANNELS:
        raise AudioFeatureError("audio-logmel-statistical-v1 requires channels=('pcm_amplitude',)")
    if series.sampling_rate_hz != _SAMPLE_RATE_HZ:
        raise AudioFeatureError("audio-logmel-statistical-v1 requires sampling_rate_hz=16000")
    if len(series.values) != _SAMPLE_COUNT:
        raise AudioFeatureError("audio-logmel-statistical-v1 requires exactly 160000 samples")


@lru_cache(maxsize=1)
def _mel_filterbank() -> tuple[tuple[float, ...], ...]:
    nyquist_hz = _SAMPLE_RATE_HZ / 2.0
    lower_mel = _hz_to_mel(0.0)
    upper_mel = _hz_to_mel(nyquist_hz)
    mel_edges = tuple(
        lower_mel + index * (upper_mel - lower_mel) / (_MEL_BAND_COUNT + 1)
        for index in range(_MEL_BAND_COUNT + 2)
    )
    hz_edges = tuple(_mel_to_hz(value) for value in mel_edges)
    frequencies = tuple(
        bin_index * _SAMPLE_RATE_HZ / _FFT_SIZE for bin_index in range(_FFT_SIZE // 2 + 1)
    )

    filters: list[tuple[float, ...]] = []
    for band in range(_MEL_BAND_COUNT):
        left = hz_edges[band]
        center = hz_edges[band + 1]
        right = hz_edges[band + 2]
        weights = tuple(
            _triangular_weight(frequency, left=left, center=center, right=right)
            for frequency in frequencies
        )
        filters.append(weights)
    return tuple(filters)


def _triangular_weight(
    frequency: float,
    *,
    left: float,
    center: float,
    right: float,
) -> float:
    if frequency <= left or frequency >= right:
        return 0.0
    if frequency <= center:
        return (frequency - left) / (center - left)
    return (right - frequency) / (right - center)


def _hz_to_mel(frequency_hz: float) -> float:
    return 2595.0 * math.log10(1.0 + frequency_hz / 700.0)


def _mel_to_hz(mel: float) -> float:
    return 700.0 * (math.pow(10.0, mel / 2595.0) - 1.0)
