"""Evaluation harness: run the pipeline over the golden set and score it.

    python eval/run_eval.py --backend stub --prompt-version v3
    python eval/run_eval.py --backend groq --prompt-version v1 v2 v3 --out eval/results

Metrics (all deterministic — no LLM judge, so the score cannot flatter itself):

  requirement recall     expected requirements matched by at least one produced requirement
  requirement precision  produced requirements that match an expected one
  distractor leakage     distractor sentences (anecdotes with no ask) that became a requirement
  traceability           produced requirements whose evidence quote is found in the notes
  priority accuracy      matched requirements with the labelled MoSCoW priority
  type accuracy          matched requirements with the labelled type
  must/should coverage   expected must/should requirements that have >=1 story
  story pass rate        stories the reviewer + guardrails passed as sprint-ready
  gherkin validity       acceptance criteria with no deterministic Gherkin issues
  generic role rate      stories whose 'as_a' is the bare word 'user'
  out-of-scope recall    labelled exclusions that appear in brief.out_of_scope
  schema repairs         LLM answers that failed schema validation and needed a repair pass
  latency / tokens       per transcript

A produced requirement matches an expected one when, for every concept group
in `must_mention`, at least one alternative appears (case-insensitive) in the
produced statement + evidence. It is a keyword rubric, so it is strict about
recall and slightly generous about precision; see eval/DECISIONS.md.
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storyforge import guardrails  # noqa: E402
from storyforge.pipeline import analyze  # noqa: E402
from storyforge.schemas import AnalysisResult  # noqa: E402

GOLDEN = Path(__file__).parent / "golden"


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("’", "'").split())


def matches(expected: dict, produced_text: str) -> bool:
    t = _norm(produced_text)
    return all(any(_norm(alt) in t for alt in group) for group in expected["must_mention"])


def score_case(case: dict, r: AnalysisResult) -> dict:
    produced = [(q, _norm(q.statement + " " + q.evidence)) for q in r.requirements]
    exp = case["expected_requirements"]

    # recall / precision with a greedy one-to-many match (an expected req may be split across produced reqs)
    matched_expected = {}
    matched_produced = set()
    for e in exp:
        for q, text in produced:
            if matches(e, text):
                matched_expected.setdefault(e["key"], []).append(q)
                matched_produced.add(q.id)
    recall = len(matched_expected) / len(exp) if exp else 1.0
    precision = len(matched_produced) / len(produced) if produced else 0.0

    # distractor leakage: a produced requirement whose evidence is mostly a distractor sentence
    leaked = 0
    for d in case.get("distractors", []):
        dn = _norm(d)
        for q, _ in produced:
            ev = _norm(q.evidence)
            if ev and (ev in dn or dn in ev or guardrails.trace_score(q.evidence, d) > 0.85):
                leaked += 1
                break

    prio_ok = type_ok = 0
    for e in exp:
        qs = matched_expected.get(e["key"])
        if not qs:
            continue
        q = qs[0]
        prio_ok += q.priority.value == e["priority"]
        type_ok += q.type.value == e["type"]
    n_matched = len(matched_expected)

    traceable = sum(bool(q.traceable) for q in r.requirements)

    # story metrics
    stories = r.backlog.stories
    reviews = {rv.story_id: rv for rv in r.reviews.reviews}
    passed = sum(1 for s in stories if s.id in reviews and reviews[s.id].passed)
    acs = [ac for s in stories for ac in s.acceptance_criteria]
    gherkin_bad = sum(1 for s in stories if guardrails.gherkin_issues(s))
    generic_role = sum(1 for s in stories if s.as_a.strip().lower() in {"user", "a user", "the user"})

    covered_req = {rid for s in stories for rid in s.requirement_ids}
    ms = [e for e in exp if e["priority"] in ("must", "should")]
    ms_covered = 0
    for e in ms:
        qs = matched_expected.get(e["key"], [])
        if any(q.id in covered_req for q in qs):
            ms_covered += 1

    oos = case.get("expected_out_of_scope", [])
    oos_hit = sum(1 for o in oos if any(_norm(o)[:25] in _norm(x) or _norm(x)[:25] in _norm(o) for x in r.brief.out_of_scope))

    repairs = sum(1 for c in r.trace.calls if not c.ok and c.error and c.error.startswith("schema"))

    return {
        "id": case["id"],
        "expected": len(exp),
        "produced": len(produced),
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "distractor_leaks": leaked,
        "distractors": len(case.get("distractors", [])),
        "traceable": traceable,
        "priority_acc": round(prio_ok / n_matched, 3) if n_matched else None,
        "type_acc": round(type_ok / n_matched, 3) if n_matched else None,
        "ms_expected": len(ms),
        "ms_covered": ms_covered,
        "stories": len(stories),
        "stories_passed": passed,
        "stories_gherkin_clean": len(stories) - gherkin_bad,
        "acs": len(acs),
        "generic_role": generic_role,
        "oos_expected": len(oos),
        "oos_hit": oos_hit,
        "review_rounds": r.trace.review_rounds,
        "revised": r.trace.stories_revised,
        "schema_repairs": repairs,
        "calls": len(r.trace.calls),
        "tokens": r.trace.total_tokens,
        "latency_s": round(r.trace.total_latency_ms / 1000, 1),
        "guardrail_flags": len(r.trace.guardrail_flags),
    }


def aggregate(rows: list[dict]) -> dict:
    def ratio(num, den):
        n, d = sum(r[num] for r in rows), sum(r[den] for r in rows)
        return round(n / d, 3) if d else None

    def mean(k):
        vals = [r[k] for r in rows if r[k] is not None]
        return round(statistics.mean(vals), 3) if vals else None

    exp_total = sum(r["expected"] for r in rows)
    matched_total = round(sum(r["recall"] * r["expected"] for r in rows))
    return {
        "cases": len(rows),
        "requirement_recall": round(matched_total / exp_total, 3),
        "requirement_precision": mean("precision"),
        "distractor_leak_rate": ratio("distractor_leaks", "distractors"),
        "traceability_rate": ratio("traceable", "produced"),
        "priority_accuracy": mean("priority_acc"),
        "type_accuracy": mean("type_acc"),
        "must_should_story_coverage": ratio("ms_covered", "ms_expected"),
        "story_pass_rate": ratio("stories_passed", "stories"),
        "gherkin_clean_rate": ratio("stories_gherkin_clean", "stories"),
        "generic_role_rate": ratio("generic_role", "stories"),
        "out_of_scope_recall": ratio("oos_hit", "oos_expected"),
        "schema_repairs_total": sum(r["schema_repairs"] for r in rows),
        "stories_revised_total": sum(r["revised"] for r in rows),
        "mean_calls": mean("calls"),
        "mean_tokens": mean("tokens"),
        "mean_latency_s": mean("latency_s"),
        "total_requirements_produced": sum(r["produced"] for r in rows),
        "total_stories": sum(r["stories"] for r in rows),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="stub")
    ap.add_argument("--prompt-version", nargs="+", default=["v3"])
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--only", nargs="*", help="case ids to run")
    ap.add_argument("--out", default=str(Path(__file__).parent / "results"))
    ap.add_argument("--save-outputs", action="store_true", help="also save each AnalysisResult json")
    a = ap.parse_args(argv)

    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLDEN.glob("*.json"))]
    if a.only:
        cases = [c for c in cases if c["id"] in a.only]
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for pv in a.prompt_version:
        rows, failures = [], []
        t0 = time.time()
        print(f"\n=== backend={a.backend} prompts={pv} rounds={a.rounds} ({len(cases)} cases) ===")
        for case in cases:
            try:
                r = analyze(case["notes"], backend=a.backend, prompt_version=pv, max_review_rounds=a.rounds)
            except Exception as e:  # noqa: BLE001 — record and continue
                failures.append({"id": case["id"], "error": str(e)[:300]})
                print(f"  ✖ {case['id']}: {str(e)[:120]}")
                continue
            row = score_case(case, r)
            rows.append(row)
            if a.save_outputs:
                (out_dir / f"{a.backend}_{pv}_{case['id']}.json").write_text(r.model_dump_json(indent=1), encoding="utf-8")
            print(
                f"  {case['id']:<34} recall {row['recall']:.2f}  prec {row['precision']:.2f}  trace {row['traceable']}/{row['produced']}  "
                f"stories {row['stories_passed']}/{row['stories']} pass  leaks {row['distractor_leaks']}/{row['distractors']}  {row['latency_s']}s"
            )
        agg = aggregate(rows) if rows else {}
        report = {
            "backend": a.backend,
            "prompt_version": pv,
            "rounds": a.rounds,
            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "wall_s": round(time.time() - t0, 1),
            "aggregate": agg,
            "cases": rows,
            "failures": failures,
        }
        path = out_dir / f"{a.backend}_{pv}.json"
        path.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print("  ---")
        for k, v in agg.items():
            print(f"  {k:<28} {v}")
        if failures:
            print(f"  failures: {len(failures)}")
        print(f"  → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
