"""Plain conversation about the selected equipment record."""

from __future__ import annotations

import json
from typing import Any

from industrial_phm.genai.local_explanation import ExplanationProvider, complete_text, select_tool


def wants_load_comparison(context: dict[str, Any], provider: ExplanationProvider) -> bool:
    messages = [
        {
            "role": "system",
            "content": (
                "사용자 질문에 필요한 동작을 하나 선택한다. "
                "전압과 부하의 관계를 조사하라는 질문에만 비교를 호출한다."
            ),
        }
    ]
    for turn in context.get("history", [])[-1:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": context["question"]})
    return (
        select_tool(
            provider,
            messages,
            {
                "reply": (
                    "선택한 기록으로 바로 답할 수 있는 일반 질문. "
                    "예: 문제 있어?, 언제부터?, 같이 달라진 신호는?"
                ),
                "compare_same_load": (
                    "전압 변화가 부하나 전류 차이와 관련 있는지 묻거나 "
                    "같은 부하에서 전압을 비교해 달라는 요청에서만 사용한다."
                ),
            },
        )
        == "compare_same_load"
    )


def generate_change_answer(
    context: dict[str, Any], provider: ExplanationProvider
) -> dict[str, str]:
    """Pass the measured record and the conversation to the model once."""
    data = {"screen": context["screen"]}
    # 역할과 말투만 말한다. '저장된 기록'이라는 틀이나 '확정할 수 없다' 같은 말을 넣으면 모델은
    # 그 말을 답으로 옮기고 질문에는 답하지 않았다.
    guidance = (
        "너는 설비 모니터링을 돕는 AI다. screen은 사용자가 지금 화면에서 보고 있는 이 설비의 "
        "데이터다. 사용자의 질문에 한국어로 바로, 사람에게 말하듯 2~4문장으로 답해라. "
        "데이터에 없는 수치는 지어내지 마라."
    )
    if (comparison := context.get("load_comparison_result")) is not None:
        data["같은 전류 범위의 실제 비교"] = comparison
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
    return {"summary": complete_text(provider, messages, max_tokens=300)}
