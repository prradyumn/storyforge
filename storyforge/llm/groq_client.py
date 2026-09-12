"""Groq — OpenAI-compatible chat completions over plain HTTPS.

No SDK: a POST with a JSON body is the whole integration, which keeps the
dependency footprint to httpx and makes the request/response shape visible.
"""
from __future__ import annotations

import os
import re

import httpx

from .base import LLMError, RateLimited, Usage, parse_json_loosely

_TRY_AGAIN = re.compile(r"try again in ([0-9.]+)(ms|s|m)", re.I)


def _retry_after(r: httpx.Response) -> float | None:
    """Groq sends Retry-After and also says 'Please try again in 7.66s' in the body."""
    if r.headers.get("retry-after"):
        try:
            return float(r.headers["retry-after"])
        except ValueError:
            pass
    m = _TRY_AGAIN.search(r.text)
    if m:
        v, unit = float(m.group(1)), m.group(2).lower()
        return v / 1000 if unit == "ms" else v * 60 if unit == "m" else v
    return None

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqClient:
    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise LLMError("GROQ_API_KEY not set")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self._http = httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> tuple[dict, Usage]:
        body = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        r = self._http.post(GROQ_URL, json=body, headers=headers)
        if r.status_code == 400 and "response_format" in r.text:
            # Some models (e.g. compound systems) reject JSON mode; fall back to prompt-only JSON.
            body.pop("response_format", None)
            r = self._http.post(GROQ_URL, json=body, headers=headers)
        if r.status_code == 429:
            raise RateLimited(r.text[:300], retry_after=_retry_after(r))
        if r.status_code >= 400:
            raise LLMError(f"groq {r.status_code}: {r.text[:300]}")
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return parse_json_loosely(text), Usage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            model=data.get("model", self.model),
            provider=self.name,
        )
