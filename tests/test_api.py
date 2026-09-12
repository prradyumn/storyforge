from fastapi.testclient import TestClient

from storyforge.api import app

client = TestClient(app)


def test_health():
    j = client.get("/api/health").json()
    assert j["ok"] and j["backends"]["stub"] and "v3" in j["prompt_versions"]


def test_index_serves_ui():
    r = client.get("/")
    assert r.status_code == 200 and "StoryForge" in r.text


def test_analyze_and_export(notes):
    r = client.post("/api/analyze", json={"notes": notes, "backend": "stub"})
    assert r.status_code == 200
    res = r.json()
    assert res["backlog"]["stories"]
    for fmt in ("brd", "backlog", "csv"):
        e = client.post("/api/export", json={"result": res, "format": fmt})
        assert e.status_code == 200 and len(e.text) > 200
    assert client.post("/api/export", json={"result": res, "format": "csv"}).text.startswith("Issue Type,Summary")


def test_analyze_validates_input():
    assert client.post("/api/analyze", json={"notes": "short"}).status_code == 422


def test_publish_dry_run_needs_no_credentials(notes):
    res = client.post("/api/analyze", json={"notes": notes, "backend": "stub"}).json()
    p = client.post("/api/publish", json={"result": res, "dry_run": True})
    assert p.status_code == 200
    j = p.json()
    assert j["dry_run"] and len(j["requests"]) == len(res["backlog"]["epics"]) + len(res["backlog"]["stories"])


def test_publish_live_without_credentials_is_a_clean_error(notes):
    res = client.post("/api/analyze", json={"notes": notes, "backend": "stub"}).json()
    p = client.post("/api/publish", json={"result": res, "dry_run": False})
    assert p.status_code == 502 and "missing Jira setting" in p.json()["detail"]
