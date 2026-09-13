import pytest

from storyforge.pipeline import analyze


def test_rejects_tiny_input():
    with pytest.raises(ValueError):
        analyze("too short", backend="stub")


def test_end_to_end_on_stub(result):
    assert result.brief.title
    assert len(result.requirements) >= 5
    assert all(r.traceable for r in result.requirements), "stub quotes sentences verbatim, so all must trace"
    assert len(result.backlog.stories) == len(result.requirements)
    assert result.trace.backend == "stub"
    assert result.trace.prompt_version == "v3"


def test_review_loop_revises_and_converges(result):
    # Stub round 1 writes generic 'user' stories -> all fail -> rewritten -> all pass in round 2
    assert result.trace.review_rounds == 2
    assert result.trace.stories_revised == len(result.backlog.stories)
    assert all(rv.passed for rv in result.reviews.reviews)
    assert all(s.review_round == 1 for s in result.backlog.stories)


def test_every_story_traces_to_a_requirement(result):
    ids = {r.id for r in result.requirements}
    for s in result.backlog.stories:
        assert s.requirement_ids and set(s.requirement_ids) <= ids


def test_zero_rounds_skips_revision(notes):
    r = analyze(notes, backend="stub", max_review_rounds=0)
    assert r.trace.review_rounds == 1 and r.trace.stories_revised == 0
    assert not any(rv.passed for rv in r.reviews.reviews)


def test_trace_records_every_call(result):
    agents = [c.agent for c in result.trace.calls]
    assert agents[:3] == ["intake", "requirements", "stories"]
    assert agents.count("review") == 2 and agents.count("stories") == 2 and agents[-1] == "gaps"
    assert all(c.ok for c in result.trace.calls)


def test_traceability_matrix(result):
    m = result.traceability_matrix()
    assert len(m) == len(result.requirements)
    assert all(row["stories"] for row in m)


def test_prompt_versions_all_run(notes):
    for v in ("v1", "v2", "v3"):
        r = analyze(notes, backend="stub", prompt_version=v, max_review_rounds=0)
        assert r.trace.prompt_version == v


def test_progress_events_follow_the_pipeline_order(notes):
    events = []
    analyze(notes, backend="stub", on_progress=events.append)
    stages = [e["stage"] for e in events if e["status"] == "running"]
    assert stages[:3] == ["intake", "requirements", "stories"]
    assert stages[-1] == "gaps"
    assert "review" in stages
    done = {e["stage"]: e for e in events if e["status"] == "done"}
    assert done["requirements"]["count"] == done["requirements"]["traceable"] > 0
    assert done["stories"]["stories"] > 0 and done["gaps"]["count"] >= 0
