from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
    FileSourceConfig,
    FileSourceMode,
    RegisteredSource,
    run_registered_file_feature_analysis,
)


def _write_csv(path: Path, *, aware: bool) -> None:
    suffix = "+00:00" if aware else ""
    path.write_text(
        "timestamp,vibration_x\n"
        f"2026-09-27T01:00:00{suffix},1.0\n"
        f"2026-09-27T01:00:01{suffix},2.0\n"
        f"2026-09-27T01:00:02{suffix},4.0\n",
        encoding="utf-8",
    )


def _source(path: Path, *, mode: FileSourceMode = FileSourceMode.SNAPSHOT) -> RegisteredSource:
    return RegisteredSource(
        source_id="field-bearing-01",
        name="Field bearing 01",
        config=FileSourceConfig(
            source_path=str(path),
            asset_id="bearing-01",
            measurement_point_id="de",
            channel_columns=("vibration_x",),
            timestamp_column="timestamp",
            sampling_rate_hz=1.0,
            mode=mode,
        ),
        registered_at=datetime(2026, 9, 27, 1, 5, tzinfo=UTC),
    )


def test_registered_file_feature_analysis_produces_run_and_feature_evidence(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "bearing.csv"
    _write_csv(source_path, aware=True)
    times = iter(
        (
            datetime(2026, 9, 27, 1, 6, tzinfo=UTC),
            datetime(2026, 9, 27, 1, 6, tzinfo=UTC) + timedelta(milliseconds=20),
        )
    )

    result = run_registered_file_feature_analysis(
        _source(source_path),
        clock=lambda: next(times),
    )

    assert result.run.asset_id == "bearing-01"
    assert result.run.source_id == "field-bearing-01"
    assert result.run.measurement_point_id == "de"
    assert result.run.observed_start_at == datetime(2026, 9, 27, 1, 0, tzinfo=UTC)
    assert result.run.observed_end_at == datetime(2026, 9, 27, 1, 0, 2, tzinfo=UTC)
    assert result.run.capability_ids == (FIELD_VIBRATION_FEATURE_CAPABILITY_ID,)
    assert len(result.run.source_snapshots) == 1
    assert result.evidence.analysis_run_id == result.run.analysis_run_id
    assert result.evidence.capability_id == FIELD_VIBRATION_FEATURE_CAPABILITY_ID
    assert result.evidence.feature_set_id == "vibration-statistical-v1"
    assert len(result.evidence.feature_names) == 8
    assert len(result.evidence.values) == 8
    assert result.evidence.source_snapshot_sha256 == result.run.source_snapshots[0].sha256


def test_registered_file_feature_analysis_rejects_naive_source_time(tmp_path: Path) -> None:
    source_path = tmp_path / "bearing.csv"
    _write_csv(source_path, aware=False)

    with pytest.raises(ValueError, match="timezone-aware source timestamps"):
        run_registered_file_feature_analysis(_source(source_path))


def test_registered_file_feature_analysis_rejects_history_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="FILE snapshot mode only"):
        run_registered_file_feature_analysis(
            _source(tmp_path, mode=FileSourceMode.HISTORY_DIRECTORY)
        )


@pytest.mark.parametrize(
    ("old", "new"),
    [("2.0", "9.0"), ("2026-09-27", "2026-09-28")],
)
def test_analysis_rejects_snapshot_replaced_between_observation_and_features(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: str, new: str
) -> None:
    from industrial_phm.application import field_analysis

    source_path = tmp_path / "bearing.csv"
    _write_csv(source_path, aware=True)
    load = field_analysis.load_registered_file_source_observation
    original_size = source_path.stat().st_size

    def load_then_replace(source):
        loaded = load(source)
        source_path.write_text(source_path.read_text().replace(old, new), encoding="utf-8")
        assert source_path.stat().st_size == original_size
        return loaded

    def unexpected_extraction(series):
        pytest.fail("changed snapshot must be rejected before feature extraction")

    monkeypatch.setattr(
        field_analysis, "load_registered_file_source_observation", load_then_replace
    )
    monkeypatch.setattr(field_analysis, "extract_vibration_features", unexpected_extraction)
    with pytest.raises(ValueError, match="source snapshot changed"):
        run_registered_file_feature_analysis(_source(source_path))


def test_analysis_requires_snapshot_evidence_before_extracting_features(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from industrial_phm.application import field_analysis

    source_path = tmp_path / "bearing.csv"
    _write_csv(source_path, aware=True)
    load = field_analysis.load_registered_file_source_observation

    def load_without_evidence(source):
        loaded = load(source)
        return replace(loaded, latest=replace(loaded.latest, source_snapshot=None))

    monkeypatch.setattr(
        field_analysis, "load_registered_file_source_observation", load_without_evidence
    )
    with pytest.raises(ValueError, match="requires source snapshot evidence"):
        run_registered_file_feature_analysis(_source(source_path))
