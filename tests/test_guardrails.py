from storyforge import guardrails as g
from storyforge.schemas import AcceptanceCriterion, Priority, Requirement, RequirementType, Story

NOTES = "Meera (Ops): We need customers to be able to start a return themselves from their order history. The return window is 30 days from delivery."


def _req(evidence, rid="R-001"):
    return Requirement(id=rid, statement="The system shall x.", type=RequirementType.FUNCTIONAL, priority=Priority.MUST, evidence=evidence)


def test_verbatim_quote_scores_one():
    assert g.trace_score("start a return themselves from their order history", NOTES) == 1.0


def test_case_and_whitespace_are_forgiven():
    assert g.trace_score("  START a return   themselves ", NOTES) == 1.0


def test_light_paraphrase_scores_high_but_below_one():
    s = g.trace_score("return window is 30 days from the delivery", NOTES)
    assert 0.82 <= s < 1.0


def test_invented_evidence_scores_low():
    assert g.trace_score("the system must support SSO login via Okta", NOTES) < 0.6


def test_check_traceability_flags_only_bad_ones():
    reqs = [_req("The return window is 30 days from delivery."), _req("Refunds go through Razorpay", "R-002")]
    flags = g.check_traceability(reqs, NOTES)
    assert reqs[0].traceable is True and reqs[1].traceable is False
    assert flags == [f"R-002: evidence not found in notes (score {reqs[1].trace_score})"]


def _story(**kw):
    base = dict(id="S-001", epic_id="E-01", title="Start a return", as_a="returning customer",
                i_want="start a return from my order history", so_that="I do not have to contact support",
                acceptance_criteria=[AcceptanceCriterion(given="an order delivered 10 days ago", when="I choose 'Return item'", then="a return is created with status 'requested' and a label is emailed")],
                requirement_ids=["R-001"], priority="must")
    base.update(kw)
    return Story(**base)


def test_good_story_has_no_issues():
    assert g.story_issues(_story(), {"R-001"}) == []


def test_generic_user_role_is_flagged():
    assert any("generic" in i for i in g.story_issues(_story(as_a="user"), {"R-001"}))


def test_vague_then_is_flagged():
    s = _story(acceptance_criteria=[AcceptanceCriterion(given="x", when="y", then="it works correctly")])
    issues = g.story_issues(s, {"R-001"})
    assert any("not observable" in i for i in issues)


def test_unknown_requirement_id_is_flagged():
    assert any("unknown requirement" in i for i in g.story_issues(_story(requirement_ids=["R-999"]), {"R-001"}))


def test_oversized_i_want_is_flagged():
    s = _story(i_want=" ".join(["word"] * 31))
    assert any("over 30 words" in i for i in g.story_issues(s, {"R-001"}))


def test_duplicate_detection():
    a = _story()
    b = _story(id="S-002", i_want="start a return from my order history page")
    c = _story(id="S-003", as_a="finance controller", i_want="see a daily refund report by reason code")
    assert ("S-001", "S-002") in g.duplicate_pairs([a, b, c])
    assert not any("S-003" in p for p in g.duplicate_pairs([a, b, c]))


def test_coverage_gap_reported():
    reqs = [_req("e", "R-001"), _req("e", "R-002")]
    from storyforge.schemas import Backlog, Epic
    bl = Backlog(epics=[Epic(id="E-01", title="t", goal="g")], stories=[_story()])
    rep = g.check_backlog(bl, reqs)
    assert rep["__coverage__"] == ["R-002 (must) has no story"]
