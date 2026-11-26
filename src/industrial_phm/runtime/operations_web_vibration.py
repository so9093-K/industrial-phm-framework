"""Representative changes in the analysed features of an asset's waveform acquisitions.

Each acquisition is one measurement with features such as RMS and kurtosis per axis. The
features are judged like stored signals: against the first 30% of the acquisitions, choosing
long, record-end and large changes. Only the vibration level (RMS) stands for a change, and only
once it reaches 1.5 times its reference or falls to two thirds of it; the other features are
reported as what moved with it. Acquisitions are placed on a time axis by their recorded
interval only to reuse that judgement; every position is reported back as an acquisition number.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.exploratory_anomaly import interval_comparison, record_changes
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_signal_comparison import (
    feature_label,
    feature_unit,
    stream_amplitude_unit,
)
from industrial_phm.application.signal_exploration import acquisition_binding
from industrial_phm.runtime.operations_web_explore import acquisition_period
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_ORIGIN = datetime(2000, 1, 1, tzinfo=UTC)
_POINTS = 1000
_SHOWN = 3
_TRACE = 48
_RELATED = 3
# Energy first, then impulsiveness: RMS shows how hard the machine vibrates, kurtosis and
# crest factor whether sharp impacts appear, as bearing faults first do.
_RANK = {"rms": 0, "excess_kurtosis": 1, "crest_factor": 2, "absolute_peak": 3, "peak_to_peak": 3}
# 대표 변화는 진동 크기(RMS)에서만 고른다. RMS는 설비를 보는 사람이 읽는 전체 진동 수준이다.
# 첨도·파고율·피크는 정상 운전 중에도 크게 오르내려 대표로 두면 경고가 떴다 사라지기를 되풀이한다.
# 이들은 같은 구간에 함께 달라진 특징으로 보인다.
_LEAD = "rms"
# 초기 수준의 1.5배~2/3 안쪽 변화는 정상 운전 중의 흔들림과 구별되지 않는다.
_MIN_RATIO = 1.5
# 진동 신호의 평균(센서 0점)과 왜도는 설비 상태로 읽히지 않아 함께 달라진 특징에서도 뺀다.
_UNREAD = frozenset({"mean", "skewness"})


def _measure(feature: str) -> str:
    return feature.rsplit(".", 1)[-1]


def feature_rank(feature: str) -> int:
    """Order in which a feature's changes are looked at, lower first."""
    return _RANK.get(_measure(feature), 4)


def acquisition_findings(
    workspace: OperationsWorkspace, asset_id: str, *, until: int | None = None
) -> dict[str, Any]:
    """Representative changes in an asset's acquisition features, by acquisition number.

    Args:
        workspace: The operations workspace.
        asset_id: The asset.

    Returns:
        The judged features and up to three changes, each with its acquisitions, reference
        values and a short trace; empty when the asset has no analysed acquisitions.
    """
    if until is not None and until < 1:
        raise ValueError("acquisition_until must be positive")
    body: dict[str, Any] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "source_id": None,
        "binding_id": None,
        "period_seconds": None,
        "first": None,
        "last": None,
        "judged": 0,
        "features": 0,
        "intervals": [],
        "meaning": "departures-from-the-first-30-percent-not-fault-diagnosis",
    }
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    if not store.path.exists():
        return body
    binding = acquisition_binding(store, asset_id)
    if binding is None:
        return body
    results, count = store.analyzed_between(
        binding.binding_id, 0, until if until is not None else 2**62, max_points=_POINTS
    )
    # 긴 기록은 이 간격으로 솎아 읽는다: 간격 안에서 떨어진 두 점은 끊긴 측정이 아니다.
    sampled = max(1, -(-count // _POINTS))
    if not results:
        return body
    period = acquisition_period(workspace, asset_id, binding.source_id)
    step = period if period and period > 0 else 1.0
    positions = [result.position for result in results]
    # A sampled record keeps every acquisition between two kept ones with the earlier.
    # The last kept result is always the record's last acquisition, so it stands for itself.
    following = dict(pairwise(positions))

    def at(position: float) -> datetime:
        return _ORIGIN + timedelta(seconds=(position - 1) * step)

    def number(moment: datetime) -> int:
        return round(1 + (moment - _ORIGIN).total_seconds() / step)

    names = sorted({name for result in results for name in (result.features or {})})
    series: dict[str, list[tuple[datetime, datetime, float]]] = {}
    for name in names:
        points = []
        for result in results:
            value = (result.features or {}).get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                end = following.get(result.position, result.position + 1)
                points.append((at(result.position), at(end), float(value)))
        if points:
            series[name] = points
    snapshots = (
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
        if workspace.acquisition_snapshot_path.is_file()
        else None
    )
    amplitude = stream_amplitude_unit(snapshots, binding.source_id, asset_id) if snapshots else None
    body.update(
        {
            "source_id": binding.source_id,
            "binding_id": binding.binding_id,
            "period_seconds": period,
            "first": positions[0],
            "last": positions[-1],
            "features": len(names),
        }
    )
    if not series:
        return body
    try:
        leads = {name: points for name, points in series.items() if _measure(name) == _LEAD}
        found = record_changes(
            leads,
            limit=_SHOWN,
            priority={name: feature_rank(name) for name in leads},
            min_ratio=_MIN_RATIO,
        )
    except LookupError, ValueError:
        return body
    body["judged"] = sum(
        row["state"] in {"scored", "level-change", "constant"} for row in found["channels"]
    )
    usual = {
        row["key"]: (row["median"], row["spread"])
        for row in found["channels"]
        if row["state"] in {"scored", "level-change"}
    }
    for item in found["intervals"]:
        name = item["channel"]
        median, spread = usual[name]
        reference = (item["baseline"]["from"], item["baseline"]["to"])
        compared = interval_comparison(series[name], reference, (item["start"], item["end"]))
        values = series[name]
        indices = sorted({round(i * (len(values) - 1) / (_TRACE - 1)) for i in range(_TRACE)})
        # Other features that moved over the same acquisitions, energy and impacts first.
        moved = []
        for other, points in series.items():
            if other == name or _measure(other) in _UNREAD:
                continue
            row = interval_comparison(points, reference, (item["start"], item["end"]))
            if row is not None and row["state"] != "within":
                moved.append((feature_rank(other), -row["distance"], other, row))
        related = [
            {
                "feature": other,
                "label": feature_label(other),
                "unit": feature_unit(other, amplitude),
                "reference": row["reference"],
                "current": row["current"],
                # 기록 끝(재생 중이면 그 위치)의 값: 이어지는 변화의 '지금'과 같은 때에 견준다.
                "latest": series[other][-1][2],
                "state": row["state"],
            }
            for _, _, other, row in sorted(moved)[:_RELATED]
        ]
        body["intervals"].append(
            {
                "feature": name,
                "label": feature_label(name),
                "unit": feature_unit(name, amplitude),
                "direction": item["direction"],
                "reason": item["reason"],
                "kind": item["kind"],
                "from": number(item["start"]),
                "to": number(item["end"]) - 1,
                "baseline": {"from": number(reference[0]), "to": number(reference[1]) - 1},
                "reference_value": compared["reference"] if compared else None,
                "typical_value": compared["current"] if compared else None,
                "reference_spread": spread,
                "change_distance": abs(compared["current"] - compared["reference"]) / spread
                if compared is not None and spread > 0
                else None,
                "value": item["value"],
                "usual": {
                    "low": median - found["threshold"] * spread,
                    "high": median + found["threshold"] * spread,
                },
                "trace": [[number(values[i][0]), values[i][2]] for i in indices],
                "trace_join": [
                    index > 0
                    and all(
                        number(values[j][0]) - number(values[j - 1][0]) <= sampled
                        for j in range(indices[index - 1] + 1, kept + 1)
                    )
                    for index, kept in enumerate(indices)
                ],
                "related": related,
            }
        )
    # 변화 구간의 앞 절반과 뒤 절반에 측정값이 각각 얼마나 움직였는지. 빨라지는지 느려지는지를
    # 예측 없이 측정값 그대로 보인다. 변화의 식별(review_key)에는 넣지 않는다.
    halves = [_halves(series[item["channel"]], item, number) for item in found["intervals"]]
    for change in body["intervals"]:
        identity = {
            "asset_id": asset_id,
            "source_id": binding.source_id,
            "binding_id": binding.binding_id,
            "change": change,
        }
        change["review_key"] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    for change, pace in zip(body["intervals"], halves, strict=True):
        change["halves"] = pace
    return body


def _halves(
    points: list[tuple[datetime, datetime, float]],
    item: dict[str, Any],
    number: Callable[[datetime], int],
) -> list[dict[str, float]] | None:
    inside = [
        (number(start), value) for start, _, value in points if item["start"] <= start < item["end"]
    ]
    if len(inside) < 6:
        return None
    middle = inside[len(inside) // 2]
    return [
        {"from": inside[0][0], "to": middle[0], "change": middle[1] - inside[0][1]},
        {"from": middle[0], "to": inside[-1][0], "change": inside[-1][1] - middle[1]},
    ]
