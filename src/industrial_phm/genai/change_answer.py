"""Plain conversation about the selected equipment record."""

from __future__ import annotations

import json
from typing import Any

from industrial_phm.genai.local_explanation import ExplanationProvider, complete_text


def generate_change_answer(
    context: dict[str, Any], provider: ExplanationProvider
) -> dict[str, str]:
    """Pass the measured record and the conversation to the model once."""
    screen = json.dumps({"screen": context["screen"]}, ensure_ascii=False, separators=(",", ":"))
    messages = [
        {
            "role": "system",
            "content": "저장된 설비 기록을 보고 질문에 짧고 자연스럽게 답한다.\n\n" + screen,
        }
    ]
    for turn in context.get("history", []):
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": context["question"]})
    return {"summary": complete_text(provider, messages, max_tokens=300)}
