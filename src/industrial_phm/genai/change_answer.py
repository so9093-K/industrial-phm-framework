"""Plain conversation about the selected equipment record."""

from __future__ import annotations

import json
from typing import Any

from industrial_phm.genai.local_explanation import ExplanationProvider, complete_chat


def generate_change_answer(
    context: dict[str, Any],
    provider: ExplanationProvider,
    *,
    analyses: dict[str, str] | None = None,
) -> dict[str, str]:
    """Ask for an answer or the additional analysis it needs to answer."""
    data: dict[str, Any] = {"screen": context["screen"]}
    # 역할과 말투만 말한다. '저장된 기록'이라는 틀이나 '확정할 수 없다' 같은 말을 넣으면 모델은
    # 그 말을 답으로 옮기고 질문에는 답하지 않았다.
    guidance = (
        "너는 설비 모니터링을 돕는 AI다. screen은 사용자가 지금 화면에서 보고 있는 이 설비의 "
        "데이터다. 사용자의 질문에 한국어로 바로, 사람에게 말하듯 2~4문장으로 답해라. "
        "데이터에 없는 수치는 지어내지 마라. 어디를 점검할지나 얼마나 급한지를 물으면 가장 크게 "
        "달라진 신호와 그 정도, 최근 움직임으로 답해라. 측정값의 변화 폭으로 설비의 긴급도나 "
        "정지 필요를 판정하지 마라. 배수는 '초기의 10배'처럼 비교 기준이 드러나게 말해라."
    )
    if "그래프(시각, 값)" in data["screen"] or "그래프(측정 번호, 값)" in data["screen"]:
        guidance += " 그래프는 일부 측정이다. 변화 시점과 비교값은 특이사항의 수치를 사용한다."
    if analyses:
        guidance += (
            " 지금 주어진 데이터로 답할 수 있으면 바로 답한다. "
            "답에 새로운 분석값이 필요한 경우에만 해당 도구 하나를 호출한다."
        )
    if context.get("active_analysis"):
        guidance += " 지금 화면의 값을 앞선 대화에서 언급한 값과 구분해 답한다."
        if analyses:
            guidance += " 현재 화면의 결과를 묻는 질문에는 바로 답한다."
    if opened := context.get("opened_view"):
        # 답과 함께 여는 분석 화면의 수치: 질문이 그 화면을 찾았으니 화면 데이터보다 앞에 둔다.
        data = opened | data
    if (comparison := context.get("load_comparison_result")) is not None:
        # 방금 실행한 비교가 이 질문의 답이다: 화면 데이터보다 앞에 둔다.
        data = {"같은 전류 범위의 실제 비교": comparison} | data
        guidance += " 같은 전류 범위의 실제 비교가 있으면 그 결과부터 말해라."
    screen = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    messages = [
        {
            "role": "system",
            "content": guidance + "\n\n" + screen,
        }
    ]
    for turn in context.get("history", []):
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": context["question"]})
    kind, value = complete_chat(provider, messages, max_tokens=300, tools=analyses)
    return {kind: value}
