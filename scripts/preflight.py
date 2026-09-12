"""Is this box (or that URL) able to serve StoryForge?

    python scripts/preflight.py                 # local checks
    python scripts/preflight.py --url https://…  # hit a deployed instance

Prints one line per check and exits non-zero if any hard check fails.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

OK, WARN, FAIL = "✔", "⚠", "✖"
results: list[tuple[str, str, str]] = []


def check(name: str, fn, hard: bool = True):
    try:
        msg = fn()
        results.append((OK, name, msg or ""))
    except Exception as e:  # noqa: BLE001
        results.append((FAIL if hard else WARN, name, str(e)[:160]))


def local_checks():
    check("python >= 3.10", lambda: sys.version.split()[0] if sys.version_info >= (3, 10) else (_ for _ in ()).throw(RuntimeError(sys.version)))
    for mod in ("fastapi", "pydantic", "httpx", "uvicorn", "dotenv"):
        check(f"import {mod}", lambda m=mod: importlib.import_module(m).__name__)
    check("package imports", lambda: importlib.import_module("storyforge.pipeline").__name__)
    check("prompts v1..v3 load", lambda: _prompts())
    check("web/index.html present", lambda: str((ROOT / "web" / "index.html").stat().st_size) + " bytes")
    check("examples present", lambda: f"{len(list((ROOT / 'examples').glob('*.txt')))} files")
    check("golden set present", lambda: f"{len(list((ROOT / 'eval' / 'golden').glob('*.json')))} cases")
    check("stub pipeline end-to-end", _stub_run)
    check("GROQ_API_KEY set", lambda: "yes" if os.environ.get("GROQ_API_KEY") else (_ for _ in ()).throw(RuntimeError("missing — live backend unavailable")), hard=False)
    check("GEMINI_API_KEY set", lambda: "yes" if os.environ.get("GEMINI_API_KEY") else (_ for _ in ()).throw(RuntimeError("missing — no fallback")), hard=False)
    check("Jira configured", lambda: "yes" if all(os.environ.get(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")) else (_ for _ in ()).throw(RuntimeError("missing — dry-run only")), hard=False)
    if os.environ.get("GROQ_API_KEY"):
        check("Groq reachable (1 tiny call)", _groq_ping, hard=False)
    if all(os.environ.get(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")):
        check("Jira reachable (/myself + project)", _jira_ping, hard=False)
    check(".env not tracked by git", _env_not_tracked)


def _prompts():
    from storyforge.prompts import AGENTS, available_versions, load_prompt

    for v in available_versions():
        for a in AGENTS:
            load_prompt(a, v)
    return ", ".join(available_versions())


def _stub_run():
    from storyforge.pipeline import analyze

    t0 = time.time()
    r = analyze((ROOT / "examples" / "returns_portal.txt").read_text(), backend="stub")
    return f"{len(r.requirements)} reqs, {len(r.backlog.stories)} stories in {time.time()-t0:.2f}s"


def _groq_ping():
    from storyforge.llm.groq_client import GroqClient

    payload, usage = GroqClient().complete_json("Return JSON.", 'Return {"ok": true}')
    return f"{usage.model} ok={payload.get('ok')}"


def _jira_ping():
    from storyforge.publishers.jira import JiraClient, JiraConfig

    c = JiraClient(JiraConfig.from_env())
    me = c.whoami()
    types = c.issue_types()
    missing = [t for t in ("Epic", "Story") if t not in types]
    if missing:
        raise RuntimeError(f"project lacks issue types {missing}; has {types}")
    return f"{me.get('displayName')} · project {c.cfg.project_key} · types {', '.join(types)}"


def _env_not_tracked():
    import subprocess

    out = subprocess.run(["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if out:
        raise RuntimeError(".env IS tracked — remove it from git now")
    return "ok"


def remote_checks(url: str):
    import httpx

    url = url.rstrip("/")
    check("GET /api/health", lambda: str(httpx.get(f"{url}/api/health", timeout=30).json().get("ok")))
    check("GET / serves UI", lambda: "StoryForge" in httpx.get(f"{url}/", timeout=30).text and "ok" or (_ for _ in ()).throw(RuntimeError("no UI")))
    check("GET /api/examples", lambda: f"{len(httpx.get(f'{url}/api/examples', timeout=30).json())} examples")

    def _analyze():
        notes = (ROOT / "examples" / "returns_portal.txt").read_text()
        t0 = time.time()
        r = httpx.post(f"{url}/api/analyze", json={"notes": notes, "backend": "stub"}, timeout=120)
        r.raise_for_status()
        return f"{len(r.json()['backlog']['stories'])} stories in {time.time()-t0:.1f}s (stub)"

    check("POST /api/analyze (stub)", _analyze)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="deployed base URL to check instead of local environment")
    a = ap.parse_args()
    remote_checks(a.url) if a.url else local_checks()
    width = max(len(n) for _, n, _ in results)
    for sym, name, msg in results:
        print(f" {sym} {name.ljust(width)}  {msg}")
    fails = sum(1 for s, _, _ in results if s == FAIL)
    warns = sum(1 for s, _, _ in results if s == WARN)
    print(f"\n {len(results)} checks · {fails} failed · {warns} warnings")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
