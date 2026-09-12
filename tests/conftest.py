import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests never touch the network: stub backend, no keys."""
    monkeypatch.setenv("STORYFORGE_BACKEND", "stub")
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "JIRA_API_TOKEN", "JIRA_BASE_URL", "JIRA_EMAIL"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(scope="session")
def notes() -> str:
    return (ROOT / "examples" / "returns_portal.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def result(notes):
    from storyforge.pipeline import analyze

    return analyze(notes, backend="stub")
