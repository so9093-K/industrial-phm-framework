"""Local physical-relation profile behind AI-Hub 239 semantic decisions.

Each relation compares channels recorded at the same source timestamp. Nulls,
conflicting duplicate values and low-signal samples are excluded and counted, so a
semantics version can be recomputed from the archive instead of from prose.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from statistics import median, quantiles

from industrial_phm.adapters.aihub_power import (
    archive_sha256,
    iter_power_observations,
    list_power_members,
)

PHASES = "RST"
MIN_CURRENT_A = 1.0
MIN_ABS_POWER_FACTOR = 0.3
MIN_PHASE_SUM = 0.5
_PHASE_POWER_CHANNELS = ("유효전력", "무효전력", "전압", "전류", "역률")

Sample = dict[str, float]
Relation = Callable[[Sample], Iterable[float] | str]


def _phase(sample: Sample, suffix: str) -> list[float] | None:
    values = [sample.get(f"{p}상{suffix}") for p in PHASES]
    return None if any(v is None for v in values) else [v for v in values if v is not None]


def _mean_ratio(average: str, suffix: str) -> Relation:
    def relation(sample: Sample) -> Iterable[float] | str:
        phases = _phase(sample, suffix)
        if average not in sample or phases is None:
            return "missing"
        if sum(phases) <= MIN_PHASE_SUM:
            return "low-signal"
        return (sample[average] / (sum(phases) / 3),)

    return relation


def _sum_ratio(total: str, suffix: str) -> Relation:
    def relation(sample: Sample) -> Iterable[float] | str:
        phases = _phase(sample, suffix)
        if total not in sample or phases is None:
            return "missing"
        if abs(sum(phases)) <= MIN_PHASE_SUM:
            return "low-signal"
        return (sample[total] / sum(phases),)

    return relation


def _line_phase(sample: Sample) -> Iterable[float] | str:
    if "선간전압평균" not in sample or "상전압평균" not in sample:
        return "missing"
    if sample["상전압평균"] <= MIN_PHASE_SUM:
        return "low-signal"
    return (sample["선간전압평균"] / sample["상전압평균"],)


def _per_phase(formula: Callable[[float, float, float, float, float], float | None]) -> Relation:
    def relation(sample: Sample) -> Iterable[float] | str:
        values = []
        for p in PHASES:
            terms = [sample.get(f"{p}상{name}") for name in _PHASE_POWER_CHANNELS]
            if any(t is None for t in terms):
                continue
            active, reactive, voltage, current, factor = (float(t) for t in terms if t is not None)
            if current < MIN_CURRENT_A or voltage <= 0:
                continue
            value = formula(active, reactive, voltage, current, factor)
            if value is not None:
                values.append(value)
        return values or "missing-or-low-signal"

    return relation


def _active(active: float, _q: float, voltage: float, current: float, pf: float) -> float | None:
    if abs(pf) < MIN_ABS_POWER_FACTOR:
        return None
    return abs(active / (voltage * current * pf))


def _apparent(active: float, reactive: float, voltage: float, current: float, _pf: float) -> float:
    return math.hypot(active, reactive) / (voltage * current)


# name -> (relation, expected value, relative tolerance, what agreement supports)
RELATIONS: dict[str, tuple[Relation, float, float, str]] = {
    "line_to_phase_voltage": (_line_phase, math.sqrt(3), 0.02, "three-phase V relation"),
    "phase_voltage_mean": (_mean_ratio("상전압평균", "전압"), 1.0, 0.01, "평균 = phase mean"),
    "line_voltage_mean": (_mean_ratio("선간전압평균", "선간전압"), 1.0, 0.01, "평균 = mean"),
    "current_mean": (_mean_ratio("전류평균", "전류"), 1.0, 0.01, "평균 = phase mean"),
    "apparent_power": (_per_phase(_apparent), 1.0, 0.05, "V and A with P/Q in W/var"),
    "active_power": (_per_phase(_active), 1.0, 0.05, "P in W, power factor as ratio"),
    "active_power_total": (_sum_ratio("유효전력평균", "유효전력"), 1.0, 0.01, "평균 = sum"),
    "reactive_power_total": (_sum_ratio("무효전력평균", "무효전력"), 1.0, 0.01, "평균 = sum"),
}
FREQUENCY_BAND_HZ = (59.5, 60.5)


def _summary(values: list[float], expected: float, tolerance: float) -> dict[str, object]:
    if not values:
        return {"evaluated": 0}
    cuts = quantiles(values, n=100) if len(values) > 1 else [values[0]] * 99
    within = sum(abs(v - expected) <= tolerance * expected for v in values)
    return {
        "evaluated": len(values),
        "median": median(values),
        "p01": cuts[0],
        "p99": cuts[98],
        "min": min(values),
        "max": max(values),
        "within_tolerance_fraction": within / len(values),
    }


def profile_member(path: Path, member: str) -> dict[str, object]:
    values: dict[str, dict[str, set[float | None]]] = defaultdict(lambda: defaultdict(set))
    for record in iter_power_observations(path, member):
        values[record.timestamp_text][record.channel_name].add(record.value)
    excluded: Counter[str] = Counter()
    samples: list[Sample] = []
    for channels in values.values():
        sample: Sample = {}
        for channel, observed in channels.items():
            if len(observed) > 1:
                excluded["conflicting-channel-values"] += 1
            elif None in observed:
                excluded["null-channel-values"] += 1
            else:
                sample[channel] = float(next(v for v in observed if v is not None))
        samples.append(sample)
    relations: dict[str, object] = {}
    for name, (relation, expected, tolerance, supports) in RELATIONS.items():
        ratios: list[float] = []
        skipped: Counter[str] = Counter()
        for sample in samples:
            result = relation(sample)
            if isinstance(result, str):
                skipped[result] += 1
            else:
                ratios.extend(result)
        relations[name] = {
            "expected": expected,
            "relative_tolerance": tolerance,
            "supports": supports,
            "skipped_timestamps": dict(skipped),
            **_summary(ratios, expected, tolerance),
        }
    frequencies = [s["주파수"] for s in samples if "주파수" in s]
    low, high = FREQUENCY_BAND_HZ
    relations["frequency_band"] = {
        "band_hz": list(FREQUENCY_BAND_HZ),
        "evaluated": len(frequencies),
        "within_band_fraction": (
            sum(low <= f <= high for f in frequencies) / len(frequencies) if frequencies else None
        ),
        "p01": quantiles(frequencies, n=100)[0] if len(frequencies) > 1 else None,
        "p99": quantiles(frequencies, n=100)[98] if len(frequencies) > 1 else None,
    }
    return {
        "member": member,
        "timestamps": len(samples),
        "excluded_channel_values": dict(excluded),
        "relations": relations,
    }


def profile_relations(path: Path, members: list[str] | None = None) -> dict[str, object]:
    selected = members or list(list_power_members(path))
    return {
        "archive": path.name,
        "archive_sha256": archive_sha256(path),
        "thresholds": {
            "min_current_a": MIN_CURRENT_A,
            "min_abs_power_factor": MIN_ABS_POWER_FACTOR,
            "min_phase_sum": MIN_PHASE_SUM,
        },
        "members": [profile_member(path, member) for member in selected],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--member", action="append", help="limit to these members")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = profile_relations(args.archive, args.member)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"profiled {args.archive.name} -> {args.output}")


if __name__ == "__main__":
    main()
