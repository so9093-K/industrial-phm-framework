import math

import pytest

from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.features import (
    AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID,
    AudioFeatureError,
    audio_logmel_feature_names,
    audio_logmel_representation_spec,
    extract_audio_logmel_features,
)


def _silent_clip(
    *,
    sampling_rate_hz: float = 16_000.0,
    channels: tuple[str, ...] = ("pcm_amplitude",),
    sample_count: int = 160_000,
) -> CanonicalTimeSeries:
    return CanonicalTimeSeries(
        asset_id="fan/section-00",
        timestamps=None,
        channels=channels,
        values=[(0.0,)] * sample_count,
        sampling_rate_hz=sampling_rate_hz,
        metadata={
            "dataset_id": "mimii-due",
            "source_group": "dev",
            "machine_type": "fan",
            "section": "00",
            "domain": "target",
            "split": "test",
            "clip_label": "anomaly",
            "source_file": "dev/fan/target_test/example.wav",
        },
    )


def test_audio_logmel_statistical_v1_has_stable_schema_and_silent_floor() -> None:
    vector = extract_audio_logmel_features(_silent_clip())

    assert vector.feature_set_id == AUDIO_LOGMEL_STATISTICAL_FEATURE_SET_ID
    assert vector.feature_names == audio_logmel_feature_names()
    assert len(vector.feature_names) == 128
    assert vector.feature_names[:4] == (
        "feature.logmel.band_00.mean",
        "feature.logmel.band_00.std",
        "feature.logmel.band_01.mean",
        "feature.logmel.band_01.std",
    )
    assert vector.feature_names[-2:] == (
        "feature.logmel.band_63.mean",
        "feature.logmel.band_63.std",
    )

    expected_floor = math.log(1e-12)
    assert vector.values[0::2] == pytest.approx((expected_floor,) * 64)
    assert vector.values[1::2] == pytest.approx((0.0,) * 64, abs=1e-12)

    record = vector.to_flat_record()
    assert record["asset_id"] == "fan/section-00"
    assert record["meta.clip_label"] == "anomaly"
    assert record["feature.logmel.band_00.mean"] == pytest.approx(expected_floor)


@pytest.mark.parametrize(
    ("sampling_rate_hz", "channels", "sample_count", "match"),
    [
        (8_000.0, ("pcm_amplitude",), 160_000, "sampling_rate_hz=16000"),
        (16_000.0, ("audio",), 160_000, "channels=\('pcm_amplitude',\)"),
        (16_000.0, ("pcm_amplitude",), 159_999, "exactly 160000 samples"),
    ],
)
def test_audio_logmel_statistical_v1_rejects_out_of_protocol_waveforms(
    sampling_rate_hz: float,
    channels: tuple[str, ...],
    sample_count: int,
    match: str,
) -> None:
    with pytest.raises(AudioFeatureError, match=match):
        extract_audio_logmel_features(
            _silent_clip(
                sampling_rate_hz=sampling_rate_hz,
                channels=channels,
                sample_count=sample_count,
            )
        )


def test_audio_logmel_statistical_v1_requires_signed_integer_pcm_scale() -> None:
    values = [(0.0,) for _ in range(160_000)]
    values[42] = (0.5,)
    series = CanonicalTimeSeries(
        asset_id="fan/section-00",
        timestamps=None,
        channels=("pcm_amplitude",),
        values=values,
        sampling_rate_hz=16_000.0,
    )

    with pytest.raises(AudioFeatureError, match="integer-valued PCM"):
        extract_audio_logmel_features(series)


def test_audio_logmel_representation_spec_exposes_reproducible_parameters() -> None:
    spec = audio_logmel_representation_spec()

    assert spec.sample_rate_hz == 16_000.0
    assert spec.sample_count == 160_000
    assert spec.pcm_full_scale_divisor == 32_768.0
    assert spec.frame_length_samples == 1_024
    assert spec.hop_length_samples == 512
    assert spec.window == "symmetric-hann"
    assert spec.centering is False
    assert spec.padding == "none"
    assert spec.fft_size == 1_024
    assert spec.mel_scale == "htk"
    assert spec.mel_band_count == 64
    assert spec.minimum_frequency_hz == 0.0
    assert spec.maximum_frequency_hz == 8_000.0
    assert spec.log_floor == 1e-12
    assert spec.frame_count == 311
    assert spec.feature_count == 128
