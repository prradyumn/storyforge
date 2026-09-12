"""Groq — OpenAI-compatible chat completions over plain HTTPS.

No SDK: a POST with a JSON body is the whole integration, which keeps the
dependency footprint to httpx and makes the request/response shape visible.
"""
from __future__ import annotations

import os

import httpx

from .base import LLMError, RateLimited, Usage, parse_json_loosely

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


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
        r = self._http.post(
            GROQ_URL,
            json=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        if r.status_code == 429:
            raise RateLimited(r.text[:300])
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
