"""Provider-agnostic LLM interface.

Each client exposes one method: complete_json(system, user) -> (dict, usage).
Keeping the surface this small is what makes the fallback router and the stub
backend trivial, and it means agents never import a vendor SDK.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    pass


class RateLimited(LLMError):
    pass


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str = ""
    provider: str = ""


class LLMClient(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> tuple[dict, Usage]:
        ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_loosely(text: str) -> dict:
    """Models sometimes wrap JSON in fences or add a sentence. Recover it."""
    text = text.strip()
    text = _FENCE.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Take the outermost {...}
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise LLMError(f"response was not JSON: {text[:200]!r}") from None
