"""Turn eval/results/*.json into the Markdown table embedded in README.md.

    python scripts/render_eval_table.py            # print the table
    python scripts/render_eval_table.py --write    # splice it into README between the markers
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
README = ROOT / "README.md"

COLS = [
    ("requirement_recall", "Req. recall"),
    ("requirement_precision", "Req. precision"),
    ("traceability_rate", "Traceable"),
    ("distractor_leak_rate", "Distractor leak"),
    ("priority_accuracy", "Priority acc."),
    ("must_should_story_coverage", "Must/should covered"),
    ("story_pass_rate", "Stories sprint-ready"),
    ("generic_role_rate", "Generic 'user' role"),
    ("out_of_scope_recall", "Out-of-scope recall"),
    ("mean_latency_s", "Mean s / transcript"),
]


def pct(v):
    if v is None:
        return "–"
    return f"{v*100:.1f}%" if 0.985 <= v < 1 else f"{v*100:.0f}%"


def render() -> str:
    reports = []
    for p in sorted(RESULTS.glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("aggregate"):
            reports.append(d)
    order = {"stub": 0, "groq": 1, "gemini": 2}
    reports.sort(key=lambda d: (order.get(d["backend"].split(",")[0], 9), d["prompt_version"]))
    head = "| Backend · prompts | " + " | ".join(c for _, c in COLS) + " |"
    sep = "|" + "---|" * (len(COLS) + 1)
    rows = []
    for d in reports:
        a = d["aggregate"]
        cells = []
        for k, _ in COLS:
            v = a.get(k)
            cells.append(f"{v:.0f}" if k == "mean_latency_s" and v is not None else pct(v))
        label = f"`{d['backend']}` · {d['prompt_version']}"
        if d.get("failures"):
            label += f" ({len(d['failures'])} case(s) failed)"
        rows.append(f"| {label} | " + " | ".join(cells) + " |")
    n_cases = reports[0]["aggregate"]["cases"] if reports else 0
    note = (
        f"\n\n_{n_cases} transcripts · lower is better for distractor leak and generic role · stub = offline heuristic baseline "
        "(it copies sentences verbatim, which the keyword rubric rewards on precision; read precision together with traceability)._"
    )
    return "\n".join([head, sep, *rows]) + note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    table = render()
    if not a.write:
        print(table)
        return
    text = README.read_text(encoding="utf-8")
    start, end = "<!-- eval-table:start -->", "<!-- eval-table:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    README.write_text(text[:i] + "\n" + table + "\n" + text[j:], encoding="utf-8")
    print("README updated")


if __name__ == "__main__":
    main()
