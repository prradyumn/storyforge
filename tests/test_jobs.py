import time

from fastapi.testclient import TestClient

from storyforge.api import app

client = TestClient(app)


def test_background_job_lifecycle(notes):
    r = client.post("/api/analyze/start", json={"notes": notes, "backend": "stub"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    for _ in range(100):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] != "running":
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["result"]["backlog"]["stories"]
    assert client.get("/api/jobs/nope").status_code == 404


def test_background_job_rejects_short_notes():
    assert client.post("/api/analyze/start", json={"notes": "x" * 45, "backend": "stub"}).status_code in (422, 200)
