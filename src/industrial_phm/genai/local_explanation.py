"""Explicitly configured, schema-constrained Chat/Responses-compatible explanation transport."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from industrial_phm.genai.analysis_explanation import (
    AnalysisExplanationError,
    _response_output_text,
)


@dataclass(frozen=True, slots=True)
class ExplanationProvider:
    base_url: str = "http://127.0.0.1:9400/v1"
    model: str = "local-main"
    api_key: str | None = None
    allow_remote: bool = False
    timeout_seconds: float = 45.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        host = parsed.hostname or ""
        try:
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.path.rstrip("/").endswith("/v1")
            or (not local and (not self.allow_remote or parsed.scheme != "https"))
        ):
            raise AnalysisExplanationError("invalid configured explanation endpoint")
        if not self.model.strip() or not 0 < self.timeout_seconds <= 120:
            raise AnalysisExplanationError("invalid explanation model or timeout")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise AnalysisExplanationError("explanation provider redirect refused")


def complete_json(
    provider: ExplanationProvider,
    messages: list[dict[str, str]],
    schema: dict[str, object],
    *,
    max_tokens: int = 1200,
) -> object:
    """One schema-constrained completion; Chat Completions first, Responses as fallback."""
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = "Bearer " + provider.api_key
    opener = build_opener(_NoRedirect())

    def post(path: str, payload: dict[str, object]) -> object:
        request = Request(
            provider.base_url.rstrip("/") + path,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers=headers,
            method="POST",
        )
        with opener.open(request, timeout=provider.timeout_seconds) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise AnalysisExplanationError("explanation response exceeds limit")
        return json.loads(data)

    named = {"name": "phm_answer", "schema": schema, "strict": True}
    try:
        try:
            data = post(
                "/chat/completions",
                {
                    "model": provider.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "response_format": {"type": "json_schema", "json_schema": named},
                },
            )
            if not isinstance(data, dict):
                raise AnalysisExplanationError("invalid chat explanation response")
            text = data["choices"][0]["message"]["content"]
        except HTTPError as error:
            # Servers without Chat schema support (or its fields) still offer Responses.
            if error.code not in {400, 404, 405, 422, 501}:
                raise
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            turns = [m for m in messages if m["role"] != "system"]
            data = post(
                "/responses",
                {
                    "model": provider.model,
                    "store": False,
                    "instructions": system,
                    "input": [{"role": m["role"], "content": m["content"]} for m in turns],
                    "max_output_tokens": max_tokens,
                    "text": {"format": {"type": "json_schema", **named}},
                },
            )
            text = _response_output_text(data)
        if not isinstance(text, str) or not text.strip():
            raise AnalysisExplanationError("empty explanation response")
        return json.loads(text)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ) as error:
        raise AnalysisExplanationError("configured explanation provider unavailable") from error


# Status verdicts the product never makes from a stored result; a score under its threshold
# is a distance from training data, not "normal". Negations such as "정상 판정이 아닙니다" pass.
_VERDICT = re.compile(
    r"정상\s*(?:범위|상태|작동|운전|가동|입니다|이다|으로\s*(?:판단|보))"
    r"|이상\s*(?:없음|이\s*없)"
    r"|고장\s*(?:입니다|상태|으로\s*판단)"
    r"|이상\s*징후(?:가)?\s*심각하지\s*않"
    r"|위험(?:이|도(?:가)?)?\s*(?:낮|적)"
)


def verdict_phrases(text: str) -> list[str]:
    """Status verdicts the explanation asserted although no stored result makes them."""
    return sorted({match.group() for match in _VERDICT.finditer(text)})
