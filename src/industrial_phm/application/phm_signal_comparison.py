"""Bounded measured-signal context for a selected pair of immutable PHM results."""

from __future__ import annotations

import math
from typing import Any

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
    read_snapshot_waveform,
)
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepResult
from industrial_phm.application.phm_read import PhmReadError
from industrial_phm.application.phm_window_read import project_phm_window
from industrial_phm.models.package import StepKind


def feature_comparison(current: StepResult, previous: StepResult | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prior = {} if previous is None else previous.features or {}
    for name, value in (current.features or {}).items():
        before = prior.get(name)
        change = None if before is None else value - before
        rows.append(
            {
                "feature": name,
                "label": feature_label(name),
                "current": value,
                "previous": before,
                "change": change,
                "relative_change_percent": None
                if before is None
                or before <= 0
                or value < 0
                or name.endswith((".mean", ".skewness", ".excess_kurtosis"))
                else 100 * (value - before) / abs(before),
            }
        )
    # Order by symmetric relative difference; neither incompatible units nor near-zero
    # denominators determine which measured features are presented first.
    rows.sort(
        key=lambda row: (
            -int(row["feature"].endswith(".rms") or "unbalance" in row["feature"]),
            -abs(row["change"] or 0) / max(abs(row["current"]), abs(row["previous"] or 0), 1e-12),
            row["feature"],
        )
    )
    return rows[:64]


def feature_label(name: str) -> str:
    electrical = {
        "current.unbalance.mean_percent": "전류 불평형 평균(%)",
        "voltage.unbalance.mean_percent": "전압 불평형 평균(%)",
        "current.three_phase_mean.std_a": "3상 평균 전류 변동(A)",
        "frequency.mean_hz": "평균 주파수(Hz)",
    }
    for phase in ("r", "s", "t"):
        electrical[f"current.phase_{phase}.mean_a"] = f"{phase.upper()}상 평균 전류(A)"
        electrical[f"voltage.phase_{phase}.mean_v"] = f"{phase.upper()}상 평균 전압(V)"
    if name in electrical:
        return electrical[name]
    labels = {
        "rms": "RMS",
        "mean": "평균",
        "standard_deviation": "표준편차",
        "absolute_peak": "절대 피크",
        "peak_to_peak": "피크-피크",
        "crest_factor": "파고율",
        "skewness": "왜도",
        "excess_kurtosis": "초과 첨도",
    }
    if name.startswith("feature."):
        channel, statistic = name.removeprefix("feature.").rsplit(".", 1)
        channel = {
            "Horizontal_vibration_signals": "수평 진동",
            "Vertical_vibration_signals": "수직 진동",
        }.get(channel, channel)
        return f"{channel} {labels.get(statistic, statistic)}"
    return name


def raw_signal_summary(
    store: SqlitePhmAnalysisStore,
    snapshots: SqliteAcquisitionSnapshotRepository,
    windows: SqliteObservationWindowRepository | None,
    binding: PhmBinding,
    result: StepResult,
) -> dict[str, Any]:
    """Read exact original input, never interpret an envelope as a waveform statistic."""
    if binding.step_kind is StepKind.ACQUISITION_SNAPSHOT:
        snapshot = snapshots.get(binding.source_id, binding.asset_id, result.position)
        if snapshot is None or snapshot.sha256 != result.input_reference.get("sha256"):
            return {"available": False, "reason": "original input identity unavailable"}
        try:
            if snapshot.sample_count > 200_000 or snapshot.file_path.stat().st_size > 16_000_000:
                return {"available": False, "reason": "original waveform exceeds summary limit"}
            waveform = read_snapshot_waveform(snapshot)
        except AcquisitionSnapshotError, OSError, UnicodeError:
            return {"available": False, "reason": "original waveform verification failed"}
        channels = [
            _summary(name, [row[i] for row in waveform.values], unit=None)
            for i, name in enumerate(waveform.channels[:16])
        ]
        return {
            "available": True,
            "kind": binding.step_kind.value,
            "sampling_rate_hz": snapshot.sampling_rate_hz,
            "sample_count": snapshot.sample_count,
            "channels": channels,
            "interpretation": "measured amplitude statistics; frequency spectrum not provided",
        }
    if windows is None or not windows.path.exists():
        return {"available": False, "reason": "original window unavailable"}
    try:
        preview = project_phm_window(
            store, windows, binding_id=binding.binding_id, position=result.position
        )
    except PhmReadError, KeyError:
        return {"available": False, "reason": "original window unavailable"}
    if not preview.get("available"):
        return {"available": False, "reason": preview.get("reason")}
    channels = []
    for channel in preview["channels"][:16]:
        points = channel["points"]
        values = [point["value"] for point in points if point["quality"] == "good"]
        summary = _summary(channel["channel_id"], values, unit=channel["unit"])
        summary["unusable_count"] = len(points) - len(values)
        channels.append(summary)
    return {"available": True, "kind": binding.step_kind.value, "channels": channels}


def _summary(channel: str, values: list[float], *, unit: str | None) -> dict[str, Any]:
    return {
        "channel": channel,
        "unit": unit,
        "count": len(values),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "mean": math.fsum(values) / len(values) if values else None,
        "rms": math.sqrt(math.fsum(v * v for v in values) / len(values)) if values else None,
    }
