"""Command line: analyse a notes file, write BRD/backlog/JSON, optionally publish.

    python -m storyforge.cli examples/returns_portal.txt --backend stub --out out/
    python -m storyforge.cli notes.txt --publish            # real Jira
    python -m storyforge.cli notes.txt --publish --dry-run  # show what would be created
    python -m storyforge.cli out/backlog.json --from-json --publish   # publish a saved result, no model calls
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import argparse
import json
import sys
from pathlib import Path

from .pipeline import analyze
from .prompts import DEFAULT_VERSION
from .publishers import jira as jira_pub
from .publishers.markdown import render_backlog, render_brd, render_csv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="storyforge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notes", help="path to a .txt/.md file of discovery notes, or '-' for stdin, or a saved backlog.json (see --from-json)")
    ap.add_argument("--from-json", action="store_true", help="treat NOTES as a saved AnalysisResult json and skip the model calls")
    ap.add_argument("--backend", default=None, help="groq,gemini | stub (default: $STORYFORGE_BACKEND)")
    ap.add_argument("--prompt-version", default=DEFAULT_VERSION)
    ap.add_argument("--rounds", type=int, default=2, help="max review/revise rounds")
    ap.add_argument("--out", default=None, help="directory to write brd.md, backlog.md, backlog.json, jira.csv")
    ap.add_argument("--publish", action="store_true", help="publish to Jira (needs JIRA_* env)")
    ap.add_argument("--dry-run", action="store_true", help="with --publish: build requests but do not send")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    if a.from_json:
        from .schemas import AnalysisResult

        result = AnalysisResult.model_validate_json(Path(a.notes).read_text(encoding="utf-8"))
    else:
        notes = sys.stdin.read() if a.notes == "-" else Path(a.notes).read_text(encoding="utf-8")
        result = analyze(notes, backend=a.backend, prompt_version=a.prompt_version, max_review_rounds=a.rounds)

    if not a.quiet:
        t = result.trace
        passed = sum(rv.passed for rv in result.reviews.reviews)
        print(f"✔ {result.brief.title}")
        print(f"  {len(result.requirements)} requirements ({sum(bool(r.traceable) for r in result.requirements)} traceable) → "
              f"{len(result.backlog.epics)} epics, {len(result.backlog.stories)} stories, {passed} sprint-ready")
        print(f"  review rounds {t.review_rounds}, revised {t.stories_revised}, gaps {len(result.gaps.gaps)}, "
              f"calls {len(t.calls)}, tokens {t.total_tokens:,}, {t.total_latency_ms/1000:.1f}s on {t.backend} [{t.prompt_version}]")
        for f in t.guardrail_flags:
            print("  ⚠", f)

    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "brd.md").write_text(render_brd(result), encoding="utf-8")
        (out / "backlog.md").write_text(render_backlog(result), encoding="utf-8")
        (out / "jira.csv").write_text(render_csv(result), encoding="utf-8")
        (out / "backlog.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        if not a.quiet:
            print(f"  wrote {out}/brd.md, backlog.md, jira.csv, backlog.json")

    if a.publish:
        cfg = None
        if a.dry_run:
            cfg = jira_pub.JiraConfig(base_url="https://example.atlassian.net", email="x", api_token="x", project_key="SF")
        rep = jira_pub.publish(result, cfg, dry_run=a.dry_run)
        if a.dry_run:
            print(f"  dry run: {len(rep.requests)} issues would be created")
            print(json.dumps(rep.requests[0], indent=1)[:800])
        else:
            print(f"  Jira: created {len(rep.created)}, skipped {len(rep.skipped)}, errors {len(rep.errors)}")
            for c in rep.created:
                print(f"   {c['kind']:5} {c['id']} → {c['url']}")
            for e in rep.errors:
                print("   ✖", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
