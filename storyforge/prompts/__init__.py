"""Versioned prompt loader.

Prompts are Markdown files under prompts/<version>/<agent>.md. The version
is part of every run trace, so an eval result can always be tied to the exact
words the model saw. Iterating a prompt means adding a new version directory,
never editing the old one — that is what lets DECISIONS.md show before/after.
"""
from __future__ import annotations

import os
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
DEFAULT_VERSION = os.environ.get("STORYFORGE_PROMPT_VERSION", "v3")

AGENTS = ("intake", "requirements", "stories", "review", "gaps")


def available_versions() -> list[str]:
    return sorted(p.name for p in PROMPTS_DIR.iterdir() if p.is_dir() and p.name.startswith("v"))


@cache
def load_prompt(agent: str, version: str = DEFAULT_VERSION) -> str:
    path = PROMPTS_DIR / version / f"{agent}.md"
    if not path.exists():
        raise FileNotFoundError(f"no prompt for agent={agent!r} version={version!r} at {path}")
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith(f"# agent: {agent}"):
        raise ValueError(f"{path} must start with '# agent: {agent}' so the stub backend can route it")
    return text
