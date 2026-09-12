"""Groq — OpenAI-compatible chat completions over plain HTTPS.

No SDK: a POST with a JSON body is the whole integration, which keeps the
dependency footprint to httpx and makes the request/response shape visible.
"""
from __future__ import annotations

import os
import re
import time
from collections import deque

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


class TokenThrottle:
    """Client-side tokens-per-minute pacing.

    Groq's free tier caps TPM per model (e.g. 30K for the model behind
    groq/compound). Rather than hit 429s and guess at back-off, we keep a
    sliding 60-second window of tokens actually used and sleep until a new
    request (estimated from prompt length + a completion allowance) fits.
    """

    def __init__(self, tpm: int, completion_allowance: int = 3000):
        self.tpm = tpm
        self.allowance = completion_allowance
        self.window: deque[tuple[float, int]] = deque()

    def _used(self, now: float) -> int:
        while self.window and now - self.window[0][0] > 60:
            self.window.popleft()
        return sum(t for _, t in self.window)

    def wait_for(self, prompt_chars: int) -> float:
        est = prompt_chars // 4 + self.allowance
        waited = 0.0
        while True:
            now = time.monotonic()
            used = self._used(now)
            if used + est <= self.tpm or not self.window:
                return waited
            sleep_for = max(0.5, 60 - (now - self.window[0][0]) + 0.2)
            if os.environ.get("STORYFORGE_VERBOSE"):
                print(f"    [groq] pacing: {used:,} tok in window, need {est:,} of {self.tpm:,} — sleeping {sleep_for:.0f}s", flush=True)
            time.sleep(sleep_for)
            waited += sleep_for

    def record(self, tokens: int) -> None:
        self.window.append((time.monotonic(), tokens))


_throttles: dict[str, TokenThrottle] = {}


def throttle_for(model: str) -> TokenThrottle | None:
    tpm = int(os.environ.get("GROQ_TPM", "0") or 0)
    if tpm <= 0:
        return None
    if model not in _throttles:
        _throttles[model] = TokenThrottle(int(tpm * 0.92))
    return _throttles[model]


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
            **({"max_completion_tokens": int(os.environ["GROQ_MAX_TOKENS"])} if os.environ.get("GROQ_MAX_TOKENS") else {}),
            **({"reasoning_effort": os.environ["GROQ_REASONING_EFFORT"]} if os.environ.get("GROQ_REASONING_EFFORT") else {}),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        throttle = throttle_for(self.model)
        if throttle:
            throttle.wait_for(len(system) + len(user))
        r = self._http.post(GROQ_URL, json=body, headers=headers)
        if r.status_code == 400 and "reasoning_effort" in r.text and "reasoning_effort" in body:
            body.pop("reasoning_effort")
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
        if throttle:
            throttle.record(int(usage.get("total_tokens") or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)) or 4000))
        return parse_json_loosely(text), Usage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            model=data.get("model", self.model),
            provider=self.name,
        )
