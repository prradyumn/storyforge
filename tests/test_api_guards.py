from fastapi.testclient import TestClient

from storyforge import api
from storyforge.api import app

client = TestClient(app)


def test_daily_budget_blocks_live_runs_but_not_stub(notes, monkeypatch):
    monkeypatch.setattr(api, "BUDGET", api.DailyBudget(1))
    monkeypatch.setenv("STORYFORGE_BACKEND", "stub")
    # live requests consume budget even though the backend resolves to stub in tests
    assert client.post("/api/analyze", json={"notes": notes}).status_code == 200
    r = client.post("/api/analyze", json={"notes": notes})
    assert r.status_code == 429 and "daily budget" in r.json()["detail"]
    assert client.post("/api/analyze", json={"notes": notes, "backend": "stub"}).status_code == 200
    assert client.get("/api/health").json()["live_runs_remaining_today"] == 0


def test_live_publish_requires_admin_key_when_set(notes, monkeypatch):
    monkeypatch.setenv("STORYFORGE_ADMIN_KEY", "s3cret")
    res = client.post("/api/analyze", json={"notes": notes, "backend": "stub"}).json()
    assert client.post("/api/publish", json={"result": res, "dry_run": True}).status_code == 200
    r = client.post("/api/publish", json={"result": res, "dry_run": False})
    assert r.status_code == 401
    # right key gets past the guard (and then fails on missing Jira creds, which is the next check)
    r = client.post("/api/publish", json={"result": res, "dry_run": False}, headers={"X-Admin-Key": "s3cret"})
    assert r.status_code == 502 and "Jira" in r.json()["detail"]
    assert client.get("/api/health").json()["publish_requires_admin_key"] is True
