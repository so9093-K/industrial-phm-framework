"""A selected measured change, its simultaneous signals and useful existing comparisons."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_range import range_analysis
from industrial_phm.application.signal_exploration import acquisition_series, acquisition_spectrum
from industrial_phm.genai.phm_answer import model_name, trend_word
from industrial_phm.runtime.operations_web_vibration import acquisition_findings
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def number(value: float) -> str:
    return f"{float(f'{value:.3g}'):,.12f}".rstrip("0").rstrip(".")


# 화면의 시각 표기(asset-timeline의 clockText)와 같은 한국 시간이다.
# 답에 나온 시각이 그래프의 시각과 맞아야 한다.
_KST = ZoneInfo("Asia/Seoul")
_STATE = {"higher": "비교 범위보다 높음", "lower": "비교 범위보다 낮음", "within": "비교 범위 안"}
# 진동 특징의 일반적인 뜻. 특징이 바뀐 순서를 해석할 때 쓰며, 이 설비의 고장 원인을 뜻하지 않는다.
_MEANING = {
    "rms": "전체 진동 에너지의 크기",
    "std": "평균을 중심으로 흔들리는 폭",
    "mean": "파형 값의 평균",
    "excess_kurtosis": "파형에 드물게 큰 충격 성분이 섞인 정도",
    "skewness": "파형 값이 한쪽으로 치우친 정도",
    "peak_to_peak": "순간 최대값과 최소값의 차이",
    "absolute_peak": "가장 큰 순간 진폭",
    "crest_factor": "RMS에 비해 순간 최대값이 큰 정도",
}


def about(value: float) -> str:
    """Two significant digits, as the screen names an operating level ('약 11 A 운전')."""
    return f"{float(f'{value:.2g}'):,.12f}".rstrip("0").rstrip(".")


def clock(at: str) -> str:
    """'10월 4일 09:19' (한국 시간)."""
    moment = datetime.fromisoformat(at).astimezone(_KST)
    return f"{moment.month}월 {moment.day}일 {moment:%H:%M}"


def _episode(
    intervals: list[dict[str, Any]],
    key: str,
    span: Callable[[dict[str, Any]], tuple[float, float]],
) -> list[dict[str, Any]]:
    """Changes chained by overlapping time with the selected one, in start order (as on screen)."""
    group: list[dict[str, Any]] = []
    end = 0.0
    for row in sorted(intervals, key=span):
        start, stop = span(row)
        if group and start <= end:
            group.append(row)
            end = max(end, stop)
            continue
        if any(member["review_key"] == key for member in group):
            break
        group, end = [row], stop
    return group if any(member["review_key"] == key for member in group) else []


def _change_target(
    row: dict[str, Any], before: float | None, after: float | None, where: str
) -> dict[str, Any]:
    """A fact about one found change: the screen draws it as that change's line and band."""
    return {
        "kind": "change",
        "review_key": row["review_key"],
        "label": row["label"],
        "before": before,
        "after": after,
        "unit": row.get("unit"),
        "where": where,
    }


def _steps(checked: dict[str, tuple[str, str]], first: tuple[str, ...]) -> list[dict[str, str]]:
    """What the investigation looked at, as '항목 · 결과' rows: the selected change first."""
    order = [key for key in first if key in checked] + [key for key in checked if key not in first]
    return [{"fact": key, "label": checked[key][0], "result": checked[key][1]} for key in order]


def _order(members: list[dict[str, Any]], start: Callable[[dict[str, Any]], str]) -> str:
    """'A·B(10월 4일 09:19) → C(10월 5일 03:05)': changes that began together share one step."""
    steps: list[tuple[str, list[str]]] = []
    for row in members:  # already in start order
        if steps and steps[-1][0] == start(row):
            steps[-1][1].append(row["label"])
        else:
            steps.append((start(row), [row["label"]]))
    return " → ".join("·".join(names) + f"({when})" for when, names in steps)


def _model_input(workspace: OperationsWorkspace, package_id: str) -> str:
    """Describe the actual input contract, without treating it as a cause of disagreement."""
    try:
        if "/" in package_id or package_id.startswith("."):
            raise ValueError("invalid package")
        package = json.loads((workspace.models_path / package_id / "package.json").read_text())
        inputs = package["input"]
        sequence = inputs.get("sequence_length", 1)
        features = inputs["feature_names"]
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence < 1
            or not isinstance(features, list)
            or not features
        ):
            raise ValueError("unknown model input")
        scope = f"연속 {sequence}회 측정의 특징 흐름" if sequence > 1 else "각 측정의 특징 조합"
        method = {
            "lstm-autoencoder-v1": "을 재구성한 오차를 자체 기준값과 비교합니다.",
            "isolation-forest-refit-v1": (
                "이 학습 분포에서 얼마나 드문지를 자체 기준값과 비교합니다."
            ),
        }.get(package.get("estimator_kind"), "을 자체 모델 기준으로 분석합니다.")
        return f"측정마다 {len(features)}개 특징을 사용하며, {scope}{method}"
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return "모델의 입력 구성을 읽지 못해 어떤 입력 차이가 있는지 확인하지 못했습니다."


def selected_change(
    workspace: OperationsWorkspace, asset: str, key: str, scope: dict[str, str] | None = None
) -> dict[str, Any]:
    from datetime import datetime

    from industrial_phm.runtime.operations_web_explore import record_findings, record_selection

    scope = record_selection(scope or {})
    if "record_until" not in scope:
        record = acquisition_findings(
            workspace,
            asset,
            until=int(scope["acquisition_until"]) if "acquisition_until" in scope else None,
        )
    else:
        record = {"intervals": []}
    change = next((row for row in record["intervals"] if row["review_key"] == key), None)
    if change is None:
        record = record_findings(
            workspace,
            asset,
            until=datetime.fromisoformat(scope["record_until"])
            if "record_until" in scope
            else None,
        )
        change = next((row for row in record["intervals"] if row["review_key"] == key), None)
        if change is None:
            raise ValueError("선택한 변화가 달라졌습니다. 기록을 다시 불러오세요.")
        return {
            "binding_id": "history:" + change["key"],
            "package_id": None,
            "analysis_run_id": None,
            "position": int(datetime.fromisoformat(change["end"]).timestamp() * 1000),
            "asset_id": asset,
            "source_id": change["source_id"],
            "change_id": key,
            "history_change": change,
            "operation": record["operation"],
            "channels": [
                row["channel"]
                for row in record["signals"]
                if row["source_id"] == change["source_id"]
                and row["measurement_point_id"] == change["measurement_point_id"]
            ],
            "signal_comparison": {"previous_position": change["baseline"]["to"]},
            "episode": [
                {
                    name: row.get(name)
                    for name in (
                        "review_key",
                        "label",
                        "key",
                        "channel",
                        "unit",
                        "direction",
                        "start",
                        "end",
                        "reference_value",
                        "typical_value",
                    )
                }
                for row in _episode(
                    record["intervals"],
                    key,
                    lambda row: (
                        datetime.fromisoformat(row["start"]).timestamp(),
                        datetime.fromisoformat(row["end"]).timestamp(),
                    ),
                )
            ],
        }
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = next(row for row in store.list_bindings() if row.binding_id == record["binding_id"])
    result = store.latest_result(
        binding.binding_id, state=StepState.ANALYZED, before_position=change["to"] + 1
    )
    if result is None:
        raise ValueError("이 변화의 분석 결과를 찾지 못했습니다.")
    return {
        "binding_id": binding.binding_id,
        "package_id": binding.package_id,
        "position": result.position,
        "analysis_run_id": result.analysis_run_id,
        "asset_id": asset,
        "source_id": binding.source_id,
        "change_id": key,
        "vibration_change": change,
        "period_seconds": record["period_seconds"],
        "signal_comparison": {"previous_position": change["baseline"]["to"]},
        "episode": [
            {
                name: row.get(name)
                for name in (
                    "review_key",
                    "label",
                    "feature",
                    "unit",
                    "direction",
                    "from",
                    "to",
                    "reference_value",
                    "typical_value",
                )
            }
            for row in _episode(record["intervals"], key, lambda row: (row["from"], row["to"]))
        ],
    }


def investigation_facts(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, Any]:
    """Reuse the same A/B computations as the screens; do not rank model score scales."""
    if "history_change" in context:
        return history_investigation(context)
    change = context["vibration_change"]
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = next(row for row in store.list_bindings() if row.binding_id == context["binding_id"])
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    baseline = change["baseline"]
    spans = [("a", baseline["from"], baseline["to"]), ("b", change["from"], change["to"])]
    features = list(
        dict.fromkeys(
            [
                change["feature"],
                *[row["feature"] for row in change["related"] if row["feature"].endswith(".rms")],
            ]
        )
    )[:3]
    profiles = acquisition_series(store, snapshots, binding, features, spans)
    facts = {
        "subject": f"{change['label']}의 특이사항 구간은 "
        f"{change['from']}~{change['to']}번째 측정입니다. "
        f"초기는 기록 처음 30%인 {baseline['from']}~{baseline['to']}번째 측정입니다.",
        "scope": "저장된 과거 측정끼리의 비교입니다.",
        "conditions": "실제 부하·회전수의 시간별 변화나 정비 이력은 "
        "이 분석에 포함되어 있지 않습니다.",
    }
    where = f"{change['from']}~{change['to']}번째 측정"
    selected = _change_target(
        change, change.get("reference_value"), change.get("typical_value"), where
    )
    targets: dict[str, dict[str, Any]] = {"subject": selected}
    # 화면이 '확인한 항목'으로 보여 줄 한 줄씩: 무엇을 봤고 결과가 어땠는지.
    checked: dict[str, tuple[str, str]] = {}
    episode = context.get("episode", [])
    others = [row for row in episode if row["review_key"] != change["review_key"]]
    for index, row in enumerate(profiles):
        a, b = row["periods"]["a"], row["periods"]["b"]
        if a.get("quantiles") is None or b.get("quantiles") is None:
            continue
        unit = row["unit"] or "(단위 미확인)"
        facts[f"feature_{index}"] = (
            f"{row['label']}의 기준 구간 중앙값 {number(a['quantiles'][2])} {unit}, "
            f"변화 구간 중앙값 {number(b['quantiles'][2])} {unit}."
        )
        member = (
            change if index == 0 else next((m for m in others if m["feature"] == row["key"]), None)
        )
        medians = a["quantiles"][2], b["quantiles"][2]
        checked[f"feature_{index}"] = (
            row["label"],
            f"{number(medians[0])} → {number(medians[1])}"
            + (f" {row['unit']}" if row["unit"] else ""),
        )
        targets[f"feature_{index}"] = (
            _change_target(member, *medians, f"{member['from']}~{member['to']}번째 측정")
            if member
            else {
                "kind": "signal",
                "label": row["label"],
                "before": medians[0],
                "after": medians[1],
                "unit": row["unit"],
            }
        )
        if row["key"].endswith(".rms") and a["quantiles"][2] > 0 and b["quantiles"][2] > 0:
            facts[f"feature_{index}"] += (
                " 변화 구간 중앙값은 기준의 약 "
                f"{number(b['quantiles'][2] / a['quantiles'][2])}배입니다."
            )
            label, result = checked[f"feature_{index}"]
            checked[f"feature_{index}"] = (
                label,
                f"{result} · 약 {number(b['quantiles'][2] / a['quantiles'][2])}배",
            )
        if index == 0:
            outside = row["comparison"].get("b_outside_a_band")
            # The profile explicitly names how many computed values were outside A's 5-95% range.
            if outside is not None:
                facts["persistence"] = (
                    f"변화 구간에서 계산한 {b['usable_count']}회 중 {outside}회가 기준 구간의 "
                    f"비교 범위({number(a['quantiles'][0])}~{number(a['quantiles'][4])} "
                    f"{unit}) 밖입니다. "
                    + (
                        "계산한 값이 모두 벗어나 있습니다."
                        if outside == b["usable_count"]
                        else "범위 안으로 돌아온 값도 있어, "
                        "이 구간 전체가 계속 벗어났다고 말할 수 없습니다."
                    )
                )
                checked["persistence"] = (
                    "기준 범위 밖 측정",
                    f"{b['usable_count']}회 중 {outside}회",
                )
            if a["sampled"] or b["sampled"]:
                facts["sampling"] = "측정이 많아 특징 비교는 각 구간에서 고른 표본에 기반합니다."
    try:
        flow = range_analysis(
            store,
            binding.binding_id,
            binding.step_kind,
            change["from"],
            change["to"],
            [change["feature"]],
        )
        shape = flow["features"].get(change["feature"])
        if shape:
            facts["flow"] = (
                f"변화 구간 안의 {change['label']} 흐름은 {trend_word(shape)}입니다. "
                + (
                    "구간 안의 표본으로 읽은 근사 흐름입니다."
                    if flow.get("sampled")
                    else "구간 안에 저장된 분석 결과의 흐름입니다."
                )
            )
            checked["flow"] = ("구간 안 흐름", trend_word(shape))
    except ValueError, LookupError:
        facts["flow"] = (
            "구간 내 흐름을 계산할 기록이 부족해, 계속 증가한 것인지는 확인하지 못했습니다."
        )
        checked["flow"] = ("구간 안 흐름", "계산할 기록 부족")
    # 지금 얼마나 커졌고 얼마나 빨리 커지는지.
    # 화면의 '지금 초기의 약 N배'·앞뒤 절반 값과 같은 수치다.
    suffix = f" {change['unit']}" if change.get("unit") else ""
    reference = change.get("reference_value")
    trace = change.get("trace") or []
    if trace and change["to"] >= trace[-1][0] and reference:
        at, value = trace[-1]
        facts["now"] = (
            f"마지막 측정({at}번째)의 {change['label']}는 {number(value)}{suffix}로, "
            f"초기 중앙값 {number(reference)}{suffix}의 약 {number(value / reference)}배입니다."
        )
        checked["now"] = (
            "지금",
            f"{number(value)}{suffix} · 초기의 약 {number(value / reference)}배",
        )
    if change.get("halves"):
        first, second = change["halves"]

        def moved(half: dict[str, float]) -> str:
            return ("+" if half["change"] > 0 else "") + number(half["change"]) + suffix

        facts["pace"] = (
            f"{change['label']}는 변화 구간 앞 절반({first['from']}~{first['to']}번째 측정) 동안 "
            f"{moved(first)}, 뒤 절반({second['from']}~{second['to']}번째 측정) 동안 "
            f"{moved(second)} 움직였습니다."
        )
        checked["pace"] = ("앞·뒤 절반", f"{moved(first)} → {moved(second)}")
    for name in ("persistence", "flow", "now", "pace"):
        if name in facts:
            targets[name] = selected
    # 화면이 같은 시기로 묶어 함께 그리는 변화: 시작 순서를 물으면 이것으로 답한다.
    for index, member in enumerate(others):
        unit = f" {member['unit']}" if member.get("unit") else ""
        before, after = member.get("reference_value"), member.get("typical_value")
        facts[f"episode_{index}"] = (
            f"같은 시기에 찾은 {member['label']} 변화: {member['from']}~{member['to']}번째 측정"
            + (
                f", 기준 구간 중앙값 {number(before)}{unit} → "
                f"변화 구간 중앙값 {number(after)}{unit}."
                if before is not None and after is not None
                else "."
            )
        )
        targets[f"episode_{index}"] = _change_target(
            member, before, after, f"{member['from']}~{member['to']}번째 측정"
        )
    if others:
        checked["episode_0"] = ("같은 시기 변화", "·".join(row["label"] for row in others))
        facts["order"] = (
            "같은 시기 변화의 시작 순서: "
            + _order(episode, lambda row: f"{row['from']}번째")
            + ". 먼저 시작한 변화가 뒤의 변화를 일으켰다는 뜻은 아닙니다."
        )
        meanings = [
            f"{row['label']}는 {_MEANING[row['feature'].rsplit('.', 1)[-1]]}"
            for row in episode
            if row["feature"].rsplit(".", 1)[-1] in _MEANING
        ]
        if meanings:
            facts["meaning"] = "특징의 일반적인 뜻: " + ", ".join(meanings) + "를 나타냅니다."
    actions = ["compare", "model"]
    try:
        spectrum = acquisition_spectrum(snapshots, binding, spans)
    except ValueError, LookupError, OSError:
        facts["spectrum"] = "원본 파형을 읽지 못해 주파수 변화를 확인하지 못했습니다."
        checked["spectrum"] = ("주파수", "원본 파형을 읽지 못함")
    else:
        actions.extend(["spectrum", "onset"])
        for index, channel in enumerate(spectrum["channels"]):
            bands = channel["band_shares"]
            if not bands or channel["power_ratio"] is None:
                continue
            band = max(bands, key=lambda item: abs(item["b"] - item["a"]))
            facts[f"spectrum_{index}"] = (
                f"{channel['label']}의 변화 구간 전체 에너지는 기준 구간의 "
                f"{number(channel['power_ratio'])}배. "
                f"{number(band['from_hz'])}~{number(band['to_hz'])} Hz 대역의 에너지 비중은 "
                f"{number(band['a'] * 100)}%에서 {number(band['b'] * 100)}%로 바뀌었습니다. "
                f"각 구간에서 고르게 고른 {len(spectrum['acquisitions']['a'])}회·"
                f"{len(spectrum['acquisitions']['b'])}회 파형의 평균입니다."
            )
            checked[f"spectrum_{index}"] = (
                f"{channel['label']} 주파수",
                f"{number(band['from_hz'])}~{number(band['to_hz'])} Hz 비중 "
                f"{number(band['a'] * 100)}% → {number(band['b'] * 100)}%",
            )
            targets[f"spectrum_{index}"] = {
                "kind": "spectrum",
                "label": channel["label"],
                "from_hz": band["from_hz"],
                "to_hz": band["to_hz"],
                "a": band["a"],
                "b": band["b"],
                "ratio": channel["power_ratio"],
            }
    for index, model in enumerate(store.list_bindings()):
        if (model.asset_id, model.source_id, model.measurement_point_id, model.step_kind) != (
            binding.asset_id,
            binding.source_id,
            binding.measurement_point_id,
            binding.step_kind,
        ):
            continue
        results, total = store.analyzed_between(
            model.binding_id, change["from"], change["to"], max_points=1000
        )
        exceeded = sum(row.output.get("exceeds_threshold") is True for row in results)
        name = model_name(
            model.package_id,
            results[-1].output.get("task") if results else None,
            model.step_kind.value,
        )
        facts[f"model_{index}"] = (
            f"{name}의 변화 구간 분석 {len(results)}회 중 기준 초과 {exceeded}회. "
            + ("전체가 아닌 표본입니다. " if len(results) < total else "")
            + "다른 모델과 척도·입력 범위가 다를 수 있어 이 횟수를 고장 확률로 해석하지 않습니다."
        )
        facts[f"model_input_{index}"] = name + ": " + _model_input(workspace, model.package_id)
        checked[f"model_{index}"] = (name, f"기준 초과 {len(results)}회 중 {exceeded}회")
    facts["model_limits"] = (
        "입력 구성과 기준 초과 횟수의 차이는 확인된 사실입니다. "
        "그러나 이 정보만으로 이번 판단 차이를 유발한 특징이나 원인을 확정하지는 못합니다. "
        "기준 초과 횟수가 적은 모델이 있다고 측정값의 변화를 없었던 것으로 해석하지 않습니다."
    )
    return {
        "facts": facts,
        "actions": actions,
        "targets": targets,
        "steps": _steps(checked, ("feature_0", "now", "pace", "persistence", "flow")),
    }


def _span(start: str, end: str) -> str:
    """'10월 4일 09:19~17:19', or both days when the change crosses midnight."""
    first, last = clock(start), clock(end)
    same_day = first.rsplit(" ", 1)[0] == last.rsplit(" ", 1)[0]
    return f"{first}~{last.rsplit(' ', 1)[1]}" if same_day else f"{first}~{last}"


def _level_flow(
    operation: dict[str, Any], names: list[str], start: str, end: str
) -> list[dict[str, Any]] | None:
    """When the dominant level changed around a change: '10월 3일 15:34~22:40 약 62 A 운전, ...'.

    The window is the change plus twice its length on each side, as the screen's zoomed view.
    """
    timeline = operation.get("timeline") or []
    bucket = float(operation.get("bucket_seconds") or 0)
    if not timeline or bucket <= 0:
        return None
    first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
    length = max(last - first, timedelta(seconds=bucket))
    low, high = first - 2 * length, last + 2 * length
    runs: list[list[Any]] = []  # [level, first at, last at, columns]
    for at, counts in timeline:
        moment = datetime.fromisoformat(at)
        if not low <= moment <= high or not sum(counts):
            continue
        level = max(range(len(counts)), key=lambda index: counts[index])
        if runs and runs[-1][0] == level:
            runs[-1][2] = moment
            runs[-1][3] += 1
        else:
            runs.append([level, moment, moment, 1])
    # 한 칸짜리 흔들림은 앞 흐름에 붙인다(띠에서도 눈에 띄지 않는다).
    merged: list[list[Any]] = []
    for run in runs:
        if merged and (run[3] == 1 or merged[-1][0] == run[0]):
            merged[-1][2], merged[-1][3] = run[2], merged[-1][3] + run[3]
        else:
            merged.append(run)
    if not merged or len(merged) > 8 or len(names) <= max(run[0] for run in merged):
        return None
    return [
        {
            "from": run[1].isoformat(),
            "to": (run[2] + timedelta(seconds=bucket)).isoformat(),
            "level": run[0],
        }
        for run in merged
    ]


def history_investigation(context: dict[str, Any]) -> dict[str, Any]:
    """Facts already computed over the selected source, operating level and A/B periods."""
    change = context["history_change"]
    unit = change["unit"] or "(단위 미확인)"
    before, after = change["reference_value"], change["typical_value"]
    before_text = number(before) if before is not None else "미확인"
    after_text = number(after) if after is not None else "미확인"
    year = datetime.fromisoformat(change["start"]).astimezone(_KST).year
    facts = {
        "subject": (
            f"{change['label']}의 특이사항 구간은 {year}년 {clock(change['start'])}부터 "
            f"{clock(change['end'])}까지입니다(한국 시간)."
        ),
        "feature_0": (
            f"{change['label']}의 초기 중앙값 {before_text} {unit}, "
            f"특이사항 구간 중앙값 {after_text} {unit}."
            + (
                f" 초기보다 {number(abs(after - before))} {unit}"
                f"({abs(after - before) / abs(before) * 100:.1f}%) "
                f"{'높습니다' if after > before else '낮습니다'}."
                if before is not None and after is not None and before
                else ""
            )
        ),
        "scope": "과거 실측 기록끼리의 비교입니다.",
        # 모르는 것은 실제로 없는 것만: 부하(전류)는 아래 load·operating_*로 넘긴다.
        "conditions": (
            "같은 출처·측정 위치·단위의 자료를 비교했습니다. 정비 기록은 이 자료에 없습니다."
        ),
    }
    selected = _change_target(change, before, after, _span(change["start"], change["end"]))
    targets: dict[str, dict[str, Any]] = {"subject": selected, "feature_0": selected}
    suffix = f" {change['unit']}" if change["unit"] else ""
    checked: dict[str, tuple[str, str]] = {
        "feature_0": (change["label"], f"{before_text} → {after_text}{suffix}")
    }
    episode = context.get("episode", [])
    others = [row for row in episode if row["review_key"] != change["review_key"]]
    operation = (
        next(
            (row for row in context["operation"] if row["key"] == change["operation"]["key"]),
            None,
        )
        if change.get("band") is not None and change.get("operation")
        else None
    )
    level = operation["levels"][change["band"] - 1] if operation else None
    # 운전 수준의 이름은 화면(record-findings의 bandName)과 같게: '약 11 A 운전'.
    unit = f" {operation['unit']}" if operation and operation.get("unit") else ""
    current = f"약 {about(level['typical'])}{unit} 운전" if operation and level else None
    # 관련 신호도 고른 신호와 같은 운전 수준의 측정끼리 비교한 값이다.
    among = f"{current} 중인 측정끼리, " if current else ""
    facts["feature_0"] = among + facts["feature_0"]
    related_rows = [
        row
        for row in change.get("related", [])
        # 운전 수준을 나눈 값과 같은 단위(전류)는 그 수준 안에서 견주면 거의 그대로다.
        # 전류가 어떻게 바뀌었는지는 load가 말한다.
        if not (current and operation and row["unit"] == operation.get("unit"))
    ]
    for index, related in enumerate(related_rows):
        facts[f"related_{index}"] = (
            f"{among}같은 기간에 {related['label']}: {number(related['reference'])} → "
            f"{number(related['current'])} {related['unit'] or ''}. "
            f"{_STATE.get(related['state'], related['state'])}."
        )
        checked[f"related_{index}"] = (
            related["label"],
            f"{number(related['reference'])} → {number(related['current'])}"
            + (f" {related['unit']}" if related["unit"] else ""),
        )
        member = next((row for row in others if row["key"] == related.get("key")), None)
        targets[f"related_{index}"] = (
            _change_target(
                member,
                related["reference"],
                related["current"],
                _span(member["start"], member["end"]),
            )
            if member
            else {
                "kind": "signal",
                "label": related["label"],
                "before": related["reference"],
                "after": related["current"],
                "unit": related["unit"],
            }
        )
    # 화면이 같은 시기로 묶어 함께 그리는 변화: 언제 무엇이 먼저 바뀌었는지 물으면 이것으로 답한다.
    for index, member in enumerate(others):
        values = member.get("reference_value"), member.get("typical_value")
        facts[f"episode_{index}"] = (
            f"같은 시기의 {member['label']} 특이사항: {clock(member['start'])}부터 "
            f"{clock(member['end'])}까지"
            + (
                f", 초기 중앙값 {number(values[0])} → 특이사항 구간 중앙값 "
                f"{number(values[1])} {member.get('unit') or ''}."
                if None not in values
                else "."
            )
        )
        targets[f"episode_{index}"] = _change_target(
            member, *values, _span(member["start"], member["end"])
        )
    if others:
        checked["episode_0"] = ("같은 시기 변화", "·".join(row["label"] for row in others))
        facts["order"] = (
            "같은 시기 특이사항의 시작 순서: "
            + _order(episode, lambda row: clock(row["start"]))
            + ". 먼저 시작한 변화가 뒤의 변화를 일으켰다는 뜻은 아닙니다."
        )
    if operation and current:
        facts["operating_level"] = (
            f"{current} 구간으로 분류한 측정끼리 비교해도 선택한 신호의 차이가 남았습니다."
        )
        checked["operating_level"] = ("같은 운전 수준끼리 비교", current)
        targets["operating_level"] = {
            "kind": "operation",
            "label": "운전 수준",
            "detail": f"{current} 중인 측정끼리 비교",
        }
        # 부하가 바뀌었는지 물으면 이 비중으로 답한다(화면의 운전 수준 띠와 같은 자료).
        shares = change["operation"]
        names = ["정지"] + [f"약 {about(row['typical'])}{unit} 운전" for row in operation["levels"]]
        if shares.get("baseline") and shares.get("interval"):
            parts = [
                f"{name} {round(a * 100)}% → {round(b * 100)}%"
                for name, a, b in zip(names, shares["baseline"], shares["interval"], strict=False)
                if round(a * 100) or round(b * 100)
            ]
            facts["operating_share"] = (
                "운전 수준별 측정 비중(초기 → 특이사항 구간): " + ", ".join(parts) + "."
            )
            # 확인한 항목에는 비교한 운전 수준의 비중만. 칸마다 한 수준만 고르는 흐름은
            # 한 시간 안에 두 수준을 오가는 설비에서 그래프의 평균 전류와 다르게 읽혀 넣지 않는다.
            band = change["band"]
            checked["operating_share"] = (
                f"{names[band]} 비중",
                f"{round(shares['baseline'][band] * 100)}% → "
                f"{round(shares['interval'][band] * 100)}%",
            )
            # 화면은 이 비중을 두 막대(비교 구간·변화 구간)로 그린다. 0번은 정지다.
            targets["operating_share"] = {
                "kind": "operation",
                "label": "운전 수준 비중",
                "detail": ", ".join(parts),
                "levels": names,
                "a": list(shares["baseline"]),
                "b": list(shares["interval"]),
            }
        runs = _level_flow(operation, names, change["start"], change["end"])
        if runs:
            flow = ", ".join(
                f"{clock(run['from'])}~{clock(run['to'])} {names[run['level']]}" for run in runs
            )
            facts["operating_flow"] = (
                "변화 구간 앞뒤의 운전 수준 흐름(화면의 운전 수준 띠와 같이 칸마다 가장 오래 "
                "운전한 수준): " + flow + "."
            )
            # 화면은 이 흐름을 작은 띠로 그리고, 가리키면 그래프 아래 운전 수준 띠를 강조한다.
            targets["operating_flow"] = {
                "kind": "operation",
                "label": "운전 수준 흐름",
                "detail": flow,
                "levels": names,
                "runs": runs,
            }
    # 같은 때의 부하: 모든 운전 수준을 합친 전류 평균(관제 알림과 같은 값).
    load = change.get("load")
    if load and load.get("reference") is not None and load.get("current") is not None:
        load_unit = f" {load['unit']}" if load.get("unit") else ""
        moved = f"{number(load['reference'])} → {number(load['current'])}{load_unit}"
        facts["load"] = (
            f"같은 때 {load['label']}(모든 운전 수준을 합친 평균): 초기 {number(load['reference'])}"
            f"{load_unit} → 특이사항 구간 {number(load['current'])}{load_unit}."
        )
        checked["load"] = (load["label"], moved)
        targets["load"] = {"kind": "operation", "label": load["label"], "detail": moved}
    actions = ["signals", "compare"]
    if any(
        all(f"{phase}상{quantity}" in context["channels"] for phase in "RST")
        for quantity in ("전압", "전류")
    ):
        actions.append("electrical")
    return {
        "facts": facts,
        "actions": actions,
        "targets": targets,
        "steps": _steps(checked, ("feature_0", "load", "operating_share", "operating_level")),
    }
