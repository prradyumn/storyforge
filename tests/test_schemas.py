import pytest
from pydantic import ValidationError

from storyforge.schemas import AcceptanceCriterion, InvestScores, Priority, Requirement, RequirementType, Story


def test_requirement_id_is_normalised():
    r = Requirement(id="r-001", statement="The system shall x.", type=RequirementType.FUNCTIONAL, priority=Priority.MUST, evidence="x")
    assert r.id == "R-001"


def test_requirement_id_must_look_right():
    with pytest.raises(ValidationError):
        Requirement(id="REQ1", statement="s", type="functional", priority="must", evidence="e")


def test_story_needs_at_least_one_ac():
    with pytest.raises(ValidationError):
        Story(id="S-001", epic_id="E-01", title="t", as_a="a", i_want="b", so_that="c", acceptance_criteria=[], requirement_ids=["R-001"], priority="must")


def test_story_points_bounded():
    with pytest.raises(ValidationError):
        Story(id="S-001", epic_id="E-01", title="t", as_a="a", i_want="b", so_that="c",
              acceptance_criteria=[AcceptanceCriterion(given="g", when="w", then="t")], requirement_ids=["R-001"], priority="must", story_points=21)


def test_invest_helpers():
    s = InvestScores(independent=5, negotiable=4, valuable=3, estimable=2, small=5, testable=5)
    assert s.total == 24 and s.minimum == 2


def test_gherkin_render():
    ac = AcceptanceCriterion(given="a return exists", when="the label is scanned", then="status is 'received'")
    assert ac.as_gherkin().startswith("Given a return exists\nWhen")
