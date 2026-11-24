"""A conversation about one selected change, grounded in that change's measured facts."""

from __future__ import annotations

import json
from typing import Any

from industrial_phm.genai.local_explanation import (
    AnalysisExplanationError,
    ExplanationProvider,
    complete_text,
)
from industrial_phm.genai.outlook_answer import _NUMBER, _normalized

# 대화다: 방금 물은 것에 문장으로 짧게 답한다. 지침은 무엇을 쓸지만 말한다. 금지 목록을 적으면
# 작은 모델은 그 말투를 따라 썼다. 답의 모양을 묶는 칸('다음에 볼 것'·후속 분석·JSON)도 두지
# 않는다: 매번 채우게 하면 모든 답이 같은 보고서 모양이 됐고, 평문으로 이어지는 대화에서는
# 모델이 JSON 대신 문장으로 답해 답 자체를 잃었다.
INSTRUCTIONS = """설비 담당자와 이 특이사항을 두고 대화합니다.
facts는 이 특이사항을 측정으로 확인한 사실이고, shown은 대화창 맨 위에 이미 보인 알림입니다.
방금 받은 질문에 한국어 1~2문장으로 바로 답합니다. shown과 앞선 대화에 이미 나온 내용은
되풀이하지 않습니다.
상태를 물으면 지금 어떤지(이어지는지 끝났는지, 지금 값)로 답합니다.
원인을 물으면 같은 때 함께 바뀐 다른 신호나 부하·운전 수준으로 답합니다.
시기나 교체를 물으면 지금 상태(now)로 답하고, facts에 pace가 있으면 앞 절반과 뒤 절반에
움직인 양으로 커지는 빠르기를 잇습니다.
facts에 있는 사실과 수치만 씁니다. 답은 평범한 문장으로만 씁니다."""


def _evidence(keys: list[str], targets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Facts the answer rests on, as what the screen can point at; one entry per drawn thing."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in keys:
        target = targets.get(key)
        if target is None:
            continue
        identity = target.get("review_key") or json.dumps(target, sort_keys=True)
        if identity not in seen:
            seen.add(identity)
            out.append({"fact": key, **target})
    return out


def asks_about_models(question: str) -> bool:
    """Model scores are read only when the question names them."""
    return any(
        word in question.lower()
        for word in ("모델", "점수", "알고리즘", "lstm", "isolation", "model")
    )


def _numbers(texts: list[str]) -> set[str]:
    return {_normalized(token) for text in texts for token in _NUMBER.findall(text)}


def _known(token: str, allowed: set[str]) -> bool:
    """A number from the record or the conversation, as written or rounded.

    Rounding is accepted to two or more significant digits: 9.3 for 9.28 and 23 for 22.7 are
    the same reading the screen shows; a bare 9 is not.
    """
    value = _normalized(token)
    if value in allowed:
        return True
    places = len(value.split(".", 1)[1]) if "." in value else 0
    if len(value.lstrip("-").replace(".", "").lstrip("0")) < 2:
        return False
    target = float(value)
    for candidate in allowed:
        try:
            number = float(candidate)
        except ValueError:
            continue
        if number != target and round(number, places) == target:
            return True
    return False


def _cited(text: str, facts: dict[str, str], targets: dict[str, Any]) -> list[str]:
    """The drawable facts whose numbers the answer used, in the order the facts were given.

    The selected change itself (``subject``) is already drawn and named on screen; citing it
    under every answer repeated the same line, so only other drawn things are cited.
    """
    used = _NUMBER.findall(text)
    selected = targets.get("subject")
    return [
        key
        for key, value in facts.items()
        if key in targets
        and targets[key] != selected
        and any(_known(token, _numbers([value])) for token in used)
    ]


def _sentence(reply: str) -> str:
    """The answer sentence of a reply; a model that still writes JSON keeps its summary."""
    text = reply.strip().strip("`").strip()
    if text.startswith("{"):
        try:
            value = json.loads(text)
        except ValueError:
            return text
        summary = value.get("summary") if isinstance(value, dict) else None
        if isinstance(summary, str):
            return summary.strip()
    return text


def generate_change_answer(
    context: dict[str, Any], provider: ExplanationProvider
) -> dict[str, Any]:
    """Answer the latest question of one change's conversation.

    Args:
        context: The selected change with its ``investigation`` (facts and drawable targets),
            the ``question``, earlier turns in ``history`` and the screen's opening notice in
            ``opening``.
        provider: The local model.

    Returns:
        The answer (``summary``) and the drawable facts whose numbers it used (``evidence``).

    Raises:
        AnalysisExplanationError: The model was unavailable or kept writing numbers that are
            not in the record or the conversation.
    """
    investigation = context["investigation"]
    facts, targets = investigation["facts"], investigation.get("targets", {})
    if not asks_about_models(context["question"]):
        facts = {key: value for key, value in facts.items() if not key.startswith("model_")}
    history = context.get("history", [])
    opening = context.get("opening") or ""
    record = {"shown": opening, "facts": facts}
    messages = [
        {
            "role": "system",
            "content": INSTRUCTIONS + "\n\n" + json.dumps(record, ensure_ascii=False),
        }
    ]
    for turn in history:
        messages += [
            {"role": "user", "content": turn["question"]},
            {"role": "assistant", "content": turn["answer"]},
        ]
    messages.append({"role": "user", "content": context["question"]})
    allowed = _numbers(
        [*facts.values(), opening, context["question"]]
        + [text for turn in history for text in (turn["question"], turn["answer"])]
    )
    for attempt in range(2):
        text = _sentence(complete_text(provider, messages, max_tokens=400))
        if text and len(text) <= 300 and all(_known(n, allowed) for n in _NUMBER.findall(text)):
            cited = _cited(text, facts, targets)
            return {"summary": text, "evidence": _evidence(cited[:3], targets)}
        if attempt == 0:
            messages.append(
                {
                    "role": "user",
                    "content": "facts와 대화에 있는 수치만 써서 두 문장 이내로 다시 답하세요.",
                }
            )
    raise AnalysisExplanationError("the answer did not keep to the record")
