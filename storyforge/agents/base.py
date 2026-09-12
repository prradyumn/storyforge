"""The agent loop every StoryForge agent shares.

    build context -> call model -> validate against schema -> repair once -> record

"Context engineering" lives here in a concrete form: an agent never gets the
whole conversation. It gets (a) its role prompt, (b) the JSON schema it must
return, (c) only the upstream artefacts it needs, wrapped in tags, and (d) the
raw notes when — and only when — grounding requires them. Everything the model
sees is assembled in `render_user()` so it can be inspected in a trace.
"""
from __future__ import annotations

import json
import time
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from ..llm.base import LLMError
from ..prompts import load_prompt
from ..schemas import LLMCall, RunTrace

T = TypeVar("T", bound=BaseModel)


class AgentError(RuntimeError):
    pass


class Agent(Generic[T]):
    name: str = ""
    output_model: type[T]
    temperature: float = 0.2

    def __init__(self, llm, prompt_version: str, trace: RunTrace):
        self.llm = llm
        self.prompt_version = prompt_version
        self.trace = trace

    # -- what subclasses override -------------------------------------------
    def render_user(self, **inputs) -> str:
        raise NotImplementedError

    # -- shared machinery ------------------------------------------------------
    def system_prompt(self) -> str:
        schema = json.dumps(self.output_model.model_json_schema(), indent=None)
        return load_prompt(self.name, self.prompt_version) + (
            "\n\n## Output format\nReturn ONLY a JSON object that validates against this JSON Schema. "
            "No prose, no markdown fences.\n" + schema
        )

    def run(self, **inputs) -> T:
        system = self.system_prompt()
        user = self.render_user(**inputs)
        last_error: str | None = None
        for attempt in (1, 2):
            t0 = time.perf_counter()
            call = LLMCall(agent=self.name, model="", provider="", prompt_version=self.prompt_version, latency_ms=0, attempt=attempt)
            try:
                payload, usage = self.llm.complete_json(system, user, temperature=self.temperature, agent=self.name)
                call.model, call.provider = usage.model, usage.provider
                call.prompt_tokens, call.completion_tokens = usage.prompt_tokens, usage.completion_tokens
                result = self.output_model.model_validate(payload)
                call.latency_ms = int((time.perf_counter() - t0) * 1000)
                self.trace.calls.append(call)
                return result
            except ValidationError as e:
                # Repair pass: show the model exactly what failed and ask again.
                last_error = e.json(indent=None)[:1500]
                call.ok, call.error = False, f"schema: {last_error[:200]}"
                call.latency_ms = int((time.perf_counter() - t0) * 1000)
                self.trace.calls.append(call)
                self.trace.guardrail_flags.append(f"{self.name}: schema repair on attempt {attempt}")
                user = user + (
                    "\n\n<validation_errors>\nYour previous answer failed validation. Fix these and return the full corrected JSON:\n"
                    + last_error
                    + "\n</validation_errors>"
                )
            except LLMError as e:
                call.ok, call.error = False, str(e)[:300]
                call.latency_ms = int((time.perf_counter() - t0) * 1000)
                self.trace.calls.append(call)
                raise AgentError(f"{self.name}: {e}") from e
        raise AgentError(f"{self.name}: output failed schema validation twice: {last_error}")


def tag(name: str, content: str) -> str:
    return f"<{name}>\n{content.strip()}\n</{name}>"


def dump(model: BaseModel | list[BaseModel]) -> str:
    if isinstance(model, list):
        return json.dumps([m.model_dump(mode="json") for m in model], ensure_ascii=False, indent=1)
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=1)
