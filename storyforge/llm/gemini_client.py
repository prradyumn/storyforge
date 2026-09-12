"""Google Gemini via the REST generateContent endpoint."""
from __future__ import annotations

import os
import re

import httpx

from .base import LLMError, RateLimited, Usage, parse_json_loosely

_RETRY_DELAY = re.compile(r'"retryDelay":\s*"([0-9.]+)s"')


def _retry_after(r: httpx.Response) -> float | None:
    if r.headers.get("retry-after"):
        try:
            return float(r.headers["retry-after"])
        except ValueError:
            pass
    m = _RETRY_DELAY.search(r.text)
    return float(m.group(1)) if m else None

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 180.0):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY not set")
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self._http = httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> tuple[dict, Usage]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        gen: dict = {"temperature": temperature, "responseMimeType": "application/json"}
        budget = os.environ.get("GEMINI_THINKING_BUDGET")
        if budget is not None and budget != "":
            gen["thinkingConfig"] = {"thinkingBudget": int(budget)}
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }
        try:
            r = self._http.post(url, params={"key": self.api_key}, json=body)
        except httpx.TimeoutException as e:
            # Long generations occasionally exceed the read timeout; treat as transient so the router retries.
            raise RateLimited(f"gemini timeout: {e}", retry_after=5.0) from e
        if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in gen:
            gen.pop("thinkingConfig")
            r = self._http.post(url, params={"key": self.api_key}, json=body)
        if r.status_code == 429:
            raise RateLimited(r.text[:300], retry_after=_retry_after(r))
        if r.status_code in (500, 502, 503, 504):
            raise RateLimited(f"gemini {r.status_code} transient: {r.text[:200]}", retry_after=8.0)
        if r.status_code >= 400:
            raise LLMError(f"gemini {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"gemini: unexpected response shape: {e}") from e
        meta = data.get("usageMetadata", {})
        return parse_json_loosely(text), Usage(
            prompt_tokens=meta.get("promptTokenCount"),
            completion_tokens=(meta.get("candidatesTokenCount") or 0) + (meta.get("thoughtsTokenCount") or 0),
            model=self.model,
            provider=self.name,
        )
