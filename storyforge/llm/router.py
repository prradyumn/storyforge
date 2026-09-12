"""Fallback chain with retries.

Order is configurable (`STORYFORGE_BACKEND=groq,gemini`). A call tries each
provider in turn; a rate limit or transport error moves to the next one. The
agent layer never knows which provider answered — it only sees the Usage.
"""
from __future__ import annotations

import os
import time

from .base import LLMClient, LLMError, RateLimited, Usage


class LLMRouter:
    def __init__(self, clients: list[LLMClient], max_attempts_per_client: int = 8, backoff_s: float = 5.0):
        if not clients:
            raise LLMError("no LLM clients configured")
        self.clients = clients
        self.max_attempts = max_attempts_per_client
        self.backoff_s = backoff_s

    @property
    def name(self) -> str:
        return "+".join(c.name for c in self.clients)

    @property
    def model(self) -> str:
        return self.clients[0].model

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2, agent: str = "") -> tuple[dict, Usage]:
        last: Exception | None = None
        for client in self.clients:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    kwargs = {"temperature": temperature}
                    if client.name == "stub":
                        kwargs["agent"] = agent
                    return client.complete_json(system, user, **kwargs)
                except RateLimited as e:
                    last = e
                    # Groq's suggested wait is optimistic under a sliding TPM window; back off harder each time.
                    wait = min(max(e.retry_after or 0, self.backoff_s * (2 ** (attempt - 1))) + 1.0, 75)
                    if os.environ.get("STORYFORGE_VERBOSE"):
                        print(f"    [{client.name}] rate limited, waiting {wait:.1f}s (attempt {attempt})", flush=True)
                    time.sleep(wait)
                except (LLMError, OSError, ValueError) as e:
                    last = e
                    break  # non-retryable on this provider, try the next
        raise LLMError(f"all providers failed: {last}")


def build_router(spec: str | None = None) -> LLMRouter:
    """Build from a comma-separated spec, e.g. 'groq,gemini' or 'stub'."""
    spec = (spec or os.environ.get("STORYFORGE_BACKEND") or "groq,gemini").lower()
    clients: list[LLMClient] = []
    for name in [s.strip() for s in spec.split(",") if s.strip()]:
        if name == "stub":
            from .stub_client import StubClient

            clients.append(StubClient())
        elif name == "groq":
            from .groq_client import GroqClient

            try:
                clients.append(GroqClient())
            except LLMError:
                continue
        elif name == "gemini":
            from .gemini_client import GeminiClient

            try:
                clients.append(GeminiClient())
            except LLMError:
                continue
        else:
            raise LLMError(f"unknown backend {name!r}")
    if not clients:
        raise LLMError(f"no usable backend in {spec!r} — set GROQ_API_KEY / GEMINI_API_KEY or use 'stub'")
    return LLMRouter(clients)
