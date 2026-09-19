import struct
import wave
from pathlib import Path

from industrial_phm.adapters import (
    MIMII_DUE_CHANNELS,
    DomainAdapter,
    MimiiDueAdapter,
)

_FRAME_COUNT = 160_000


def _write_wav(path: Path, prefix_samples: tuple[int, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = struct.pack(f"<{len(prefix_samples)}h", *prefix_samples)
    padding = b"\x00\x00" * (_FRAME_COUNT - len(prefix_samples))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(prefix + padding)


def test_mimii_adapter_maps_pcm_clip_without_normalization(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "dev"
        / "fan"
        / "train"
        / "section_00_source_train_normal_0007_strenght_1_ambient.wav"
    )
    _write_wav(path, (-32_768, -1, 0, 1, 32_767))

    adapter = MimiiDueAdapter()
    series = next(iter(adapter.iter_series(tmp_path)))

    assert isinstance(adapter, DomainAdapter)
    assert adapter.domain == "mimii-due"
    assert series.asset_id == "fan/section-00"
    assert series.timestamps is None
    assert series.channels == MIMII_DUE_CHANNELS
    assert series.sampling_rate_hz == 16_000.0
    assert len(series.values) == _FRAME_COUNT
    assert series.values[:5] == (
        (-32_768.0,),
        (-1.0,),
        (0.0,),
        (1.0,),
        (32_767.0,),
    )
    assert series.labels is None
    assert series.rul is None
    assert series.metadata["dataset_id"] == "mimii-due"
    assert series.metadata["source_group"] == "dev"
    assert series.metadata["machine_type"] == "fan"
    assert series.metadata["section"] == "00"
    assert series.metadata["domain"] == "source"
    assert series.metadata["split"] == "train"
    assert series.metadata["clip_label"] == "normal"
    assert series.metadata["source_file_number"] == 7
    assert series.metadata["raw_attribute"] == "strenght_1_ambient"
    assert series.metadata["sample_encoding"] == "pcm-s16le"
    assert series.metadata["sample_width_bits"] == 16
    assert series.metadata["source_file"] == (
        "dev/fan/train/section_00_source_train_normal_0007_strenght_1_ambient.wav"
    )


def test_mimii_adapter_keeps_clip_label_in_metadata_not_sample_labels(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "dev"
        / "pump"
        / "target_test"
        / "section_02_target_test_anomaly_0042.wav"
    )
    _write_wav(path, (123,))

    series = next(iter(MimiiDueAdapter().iter_series(tmp_path)))

    assert series.asset_id == "pump/section-02"
    assert series.labels is None
    assert series.rul is None
    assert series.metadata["domain"] == "target"
    assert series.metadata["split"] == "test"
    assert series.metadata["clip_label"] == "anomaly"
    assert series.metadata["source_file_number"] == 42
    assert series.metadata["raw_attribute"] is None
