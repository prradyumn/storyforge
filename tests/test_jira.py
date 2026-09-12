from storyforge.publishers import jira as j
from storyforge.publishers.markdown import render_backlog, render_brd, render_csv


def test_build_requests_shape(result):
    cfg = j.JiraConfig(base_url="https://x.atlassian.net", email="e", api_token="t", project_key="SF")
    epics, stories = j.build_requests(result, cfg, label="sf-test")
    assert len(epics) == len(result.backlog.epics) and len(stories) == len(result.backlog.stories)
    s = stories[0]
    assert s["project"] == {"key": "SF"} and s["issuetype"] == {"name": "Story"}
    assert s["description"]["type"] == "doc" and s["description"]["version"] == 1
    assert "sf-test" in s["labels"] and s["priority"]["name"] in j.PRIORITY_MAP.values()
    assert s["_sf_epic"] == result.backlog.stories[0].epic_id


def test_description_contains_gherkin_and_traceability(result):
    s = result.backlog.stories[0]
    doc = j.story_description(s, {r.id: r.statement for r in result.requirements})
    text = str(doc)
    assert "Given " in text and "Then " in text and s.requirement_ids[0] in text


def test_dry_run_publish(result):
    cfg = j.JiraConfig(base_url="https://x.atlassian.net", email="e", api_token="t", project_key="SF")
    rep = j.publish(result, cfg, dry_run=True)
    assert rep.dry_run and not rep.created and len(rep.requests) == len(result.backlog.epics) + len(result.backlog.stories)


def test_config_from_env_errors_clearly(monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    try:
        j.JiraConfig.from_env()
    except j.JiraError as e:
        assert "JIRA_BASE_URL" in str(e)
    else:
        raise AssertionError("expected JiraError")


def test_markdown_renderers(result):
    brd, bl, csv = render_brd(result), render_backlog(result), render_csv(result)
    assert "## 5. Requirements" in brd and "Traceability matrix" in bl
    assert csv.count("\n") >= len(result.backlog.stories)
    for r in result.requirements:
        assert r.id in brd
