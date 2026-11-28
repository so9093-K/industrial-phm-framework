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
    guidance = (
        "너는 설비 모니터링을 돕는 AI다. screen은 사용자가 지금 화면에서 보고 있는 이 설비의 "
        "데이터다. 주어진 측정과 비교 조건으로 사용자의 질문에 자연스러운 한국어로 답해라. "
        "수치 변화는 '222 V에서 226 V로'처럼 문장으로 쓴다. "
        "저장 기록이나 모델 점수로 지금 설비의 정상 여부, 긴급도나 정지 필요를 단정하지 마라."
    )
    if year := context.get("record_year"):
        guidance += f" 질문의 대상인 변화는 {year}년 기록이다."
    if "그래프(시각, 값)" in data["screen"] or "그래프(측정 번호, 값)" in data["screen"]:
        guidance += " 그래프는 일부 측정이다. 변화 시점과 비교값은 특이사항의 수치를 사용한다."
    if "함께 관찰한 변화" in data["screen"]:
        guidance += (
            " 어떤 일이 있었는지 묻는 질문에는 함께 관찰한 변화와 "
            "그 전압을 비교한 운전 수준도 설명한다. "
            "함께 변했다는 관측에서 원인을 단정하지 않는다."
        )
    if analyses:
        guidance += (
            " 지금 주어진 데이터로 답할 수 있으면 바로 답한다. "
            "답에 새로운 분석값이 필요한 경우에만 해당 도구 하나를 호출한다. "
            "분석 화면은 도구 설명의 작은따옴표 속 이름으로 부른다."
        )
    if context.get("active_analysis"):
        guidance += " 지금 화면의 값을 앞선 대화에서 언급한 값과 구분해 답한다."
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
