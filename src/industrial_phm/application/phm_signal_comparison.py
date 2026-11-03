"""Bounded measured-signal context for a selected pair of immutable PHM results."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
    read_snapshot_waveform,
)
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepResult
from industrial_phm.application.phm_read import PhmReadError
from industrial_phm.application.phm_window_read import project_phm_window
from industrial_phm.models.package import StepKind, fit_row_ranges

# Waveform features measured in the signal's own amplitude unit; the others are ratios.
AMPLITUDE_FEATURES = ("mean", "rms", "standard_deviation", "absolute_peak", "peak_to_peak")


def stream_amplitude_unit(
    snapshots: SqliteAcquisitionSnapshotRepository, source_id: str, asset_id: str
) -> str | None:
    """The amplitude unit an acquisition stream declares for its waveforms, if any."""
    for stream in snapshots.list_streams():
        if stream.asset_id == asset_id and stream.source_id == source_id:
            unit = stream.metadata.get("amplitude_unit")
            return unit if isinstance(unit, str) and unit.strip() else None
    return None


def feature_unit(feature: str, amplitude_unit: str | None) -> str | None:
    """A waveform feature's unit: the amplitude unit for amplitude features, none for ratios."""
    return amplitude_unit if feature.rsplit(".", 1)[-1] in AMPLITUDE_FEATURES else None


def with_units(rows: list[dict[str, Any]], amplitude_unit: str | None) -> list[dict[str, Any]]:
    """Comparison rows with each feature's unit, for screens that print the values."""
    return [
        {**row, "unit": feature_unit(str(row.get("feature", "")), amplitude_unit)} for row in rows
    ]


# Where an asset usually sits: the 5-95% range of each feature over the analyzed results before
# the comparison, once there are enough of them to call it usual.
USUAL_QUANTILES = (0.05, 0.95)
MIN_USUAL_RESULTS = 20


def usual_ranges(results: Sequence[StepResult], names: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Each named feature's usual range over earlier analyzed results of the same model."""
    ranges: dict[str, dict[str, Any]] = {}
    for name in names:
        values = np.asarray(
            [
                value
                for result in results
                if isinstance(value := (result.features or {}).get(name), (int, float))
                and math.isfinite(value)
            ],
            dtype=float,
        )
        if values.size < MIN_USUAL_RESULTS:
            continue
        low, high = np.quantile(values, USUAL_QUANTILES)
        ranges[name] = {"low": float(low), "high": float(high), "results": int(values.size)}
    return ranges


# Earlier results read, evenly over the record, to find each feature's usual range.
USUAL_MAX_RESULTS = 2000


def attach_usual_ranges(
    store: SqlitePhmAnalysisStore, binding_id: str, rows: list[dict[str, Any]], before: int
) -> int | None:
    """Give each compared feature its usual range over results up to ``before``.

    ``before`` is the last result read: just ahead of the earlier of the two compared results,
    so neither of them shapes what counts as usual. Returns it when any range was found.
    """
    earlier = (
        store.analyzed_between(binding_id, 1, before, max_points=USUAL_MAX_RESULTS)[0]
        if before >= 1
        else ()
    )
    usual = usual_ranges(earlier, [row["feature"] for row in rows])
    for row in rows:
        row["usual"] = usual.get(row["feature"])
    return before if usual else None


def attach_learned_ranges(models_root: Path, package_id: str, rows: list[dict[str, Any]]) -> None:
    """Give each compared feature the range the model was fitted on, when the package kept it.

    A value inside the asset's usual range but outside this one is a state the model never
    learned, which reads differently from a value the asset itself rarely shows.
    """
    learned = fit_row_ranges(models_root / package_id, USUAL_QUANTILES)
    for row in rows:
        edges = learned.get(row["feature"])
        row["learned"] = None if edges is None else {"low": edges[0], "high": edges[1]}


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


_HISTORY_STATS = {"mean": "평균", "std": "표준편차", "min": "최소", "max": "최대"}


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
    # Stored-history window statistics (ADR-0032): "<channel>.<mean|std|min|max>".
    channel, _, statistic = name.rpartition(".")
    if channel and not name.startswith("feature.") and statistic in _HISTORY_STATS:
        return f"{channel} {_HISTORY_STATS[statistic]}"
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
