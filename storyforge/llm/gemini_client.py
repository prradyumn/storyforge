"""Google Gemini via the REST generateContent endpoint."""
from __future__ import annotations

import os

import httpx

from .base import LLMError, RateLimited, Usage, parse_json_loosely

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY not set")
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self._http = httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> tuple[dict, Usage]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        }
        r = self._http.post(url, params={"key": self.api_key}, json=body)
        if r.status_code == 429:
            raise RateLimited(r.text[:300])
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
            completion_tokens=meta.get("candidatesTokenCount"),
            model=self.model,
            provider=self.name,
        )
