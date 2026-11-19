"""One selected vibration change read together with the existing comparison and spectrum."""

from __future__ import annotations

import json
from typing import Any

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_range import range_analysis
from industrial_phm.application.signal_exploration import acquisition_series, acquisition_spectrum
from industrial_phm.genai.phm_answer import model_name, trend_word
from industrial_phm.runtime.operations_web_vibration import acquisition_findings
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def number(value: float) -> str:
    return f"{float(f'{value:.3g}'):,.12f}".rstrip("0").rstrip(".")


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


def selected_change(workspace: OperationsWorkspace, asset: str, key: str) -> dict[str, Any]:
    record = acquisition_findings(workspace, asset)
    change = next((row for row in record["intervals"] if row["review_key"] == key), None)
    if change is None:
        raise ValueError("선택한 진동 변화가 달라졌습니다. 요약을 다시 불러오세요.")
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
    }


def investigation_facts(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, Any]:
    """Reuse the same A/B computations as the screens; do not rank model score scales."""
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
        "subject": f"{change['label']}의 주요 변화로 고른 구간은 "
        f"{change['from']}~{change['to']}번째 측정입니다. "
        f"비교 기준은 기록 처음 30%인 {baseline['from']}~{baseline['to']}번째 측정이며 "
        "정상 구간으로 판정한 것은 아닙니다.",
        "scope": "저장된 과거 측정의 변화입니다. 이 기록 이후 실제 설비 상태는 알 수 없습니다.",
        "conditions": "실제 부하·회전수의 시간별 변화나 정비 이력은 "
        "이 분석에 포함되어 있지 않습니다.",
    }
    for index, row in enumerate(profiles):
        a, b = row["periods"]["a"], row["periods"]["b"]
        if a.get("quantiles") is None or b.get("quantiles") is None:
            continue
        unit = row["unit"] or "(단위 미확인)"
        facts[f"feature_{index}"] = (
            f"{row['label']}의 기준 구간 중앙값 {number(a['quantiles'][2])} {unit}, "
            f"변화 구간 중앙값 {number(b['quantiles'][2])} {unit}."
        )
        if row["key"].endswith(".rms") and a["quantiles"][2] > 0 and b["quantiles"][2] > 0:
            facts[f"feature_{index}"] += (
                " 변화 구간 중앙값은 기준의 약 "
                f"{number(b['quantiles'][2] / a['quantiles'][2])}배입니다."
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
    except ValueError, LookupError:
        facts["flow"] = (
            "구간 내 흐름을 계산할 기록이 부족해, 계속 증가한 것인지는 확인하지 못했습니다."
        )
    actions = ["compare", "model"]
    try:
        spectrum = acquisition_spectrum(snapshots, binding, spans)
    except ValueError, LookupError, OSError:
        facts["spectrum"] = "원본 파형을 읽지 못해 주파수 변화를 확인하지 못했습니다."
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
    facts["model_limits"] = (
        "입력 구성과 기준 초과 횟수의 차이는 확인된 사실입니다. "
        "그러나 이 정보만으로 이번 판단 차이를 유발한 특징이나 원인을 확정하지는 못합니다. "
        "기준 초과 횟수가 적은 모델이 있다고 측정값의 변화를 없었던 것으로 해석하지 않습니다."
    )
    return {"facts": facts, "actions": actions}
