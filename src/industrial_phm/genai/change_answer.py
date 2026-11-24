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
    guidance = "저장된 설비 기록을 보고 질문에 짧고 자연스럽게 답한다."
    if (comparison := context.get("load_comparison_result")) is not None:
        data["같은 전류 범위의 실제 비교"] = comparison
        guidance += (
            " 계산 결과가 있으면 같은 전류 범위에서 확인한 차이부터 설명한다."
            " 원인은 이 비교로 확정할 수 없다."
        )
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
