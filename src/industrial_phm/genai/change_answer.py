"""Plain conversation about the selected equipment record."""

from __future__ import annotations

import json
from typing import Any

from industrial_phm.genai.local_explanation import ExplanationProvider, complete_text, select_tool


def choose_analysis(context: dict[str, Any], provider: ExplanationProvider) -> str | None:
    """The analysis this question needs, among those the change can open, or None to just reply.

    The model reads the screens' names and what each shows; the product runs or opens the one
    it picks with this change's own signal and periods.
    """
    analyses: dict[str, str] = context.get("analyses") or {}
    if not analyses:
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "사용자 질문에 함께 보여 줄 분석을 하나 고른다. "
                "화면 데이터로 바로 답하면 되는 질문이면 reply를 고른다."
            ),
        }
    ]
    for turn in context.get("history", [])[-1:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": context["question"]})
    tools = {"reply": "화면 데이터로 바로 답한다."} | analyses
    chosen = select_tool(provider, messages, tools)
    return chosen if chosen in analyses else None


def generate_change_answer(
    context: dict[str, Any], provider: ExplanationProvider
) -> dict[str, str]:
    """Pass the measured record and the conversation to the model once."""
    data: dict[str, Any] = {"screen": context["screen"]}
    # 역할과 말투만 말한다. '저장된 기록'이라는 틀이나 '확정할 수 없다' 같은 말을 넣으면 모델은
    # 그 말을 답으로 옮기고 질문에는 답하지 않았다.
    guidance = (
        "너는 설비 모니터링을 돕는 AI다. screen은 사용자가 지금 화면에서 보고 있는 이 설비의 "
        "데이터다. 사용자의 질문에 한국어로 바로, 사람에게 말하듯 2~4문장으로 답해라. "
        "데이터에 없는 수치는 지어내지 마라."
    )
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
    return {"summary": complete_text(provider, messages, max_tokens=300)}
