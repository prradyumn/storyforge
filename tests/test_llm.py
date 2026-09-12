"""Provider-layer behaviour that must hold without any network."""
import time
from collections import deque

from storyforge.llm.base import parse_json_loosely
from storyforge.llm.groq_client import TokenThrottle, _retry_after


class _Resp:
    def __init__(self, headers=None, text=""):
        self.headers = headers or {}
        self.text = text


def test_retry_after_from_header():
    assert _retry_after(_Resp({"retry-after": "7"})) == 7.0


def test_retry_after_from_groq_body():
    assert _retry_after(_Resp(text="... Please try again in 3.838s. ...")) == 3.838
    assert _retry_after(_Resp(text="try again in 250ms")) == 0.25
    assert _retry_after(_Resp(text="try again in 1m")) == 60.0
    assert _retry_after(_Resp(text="no hint here")) is None


def test_parse_json_loosely_recovers_fenced_and_prefixed():
    assert parse_json_loosely('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loosely('Sure! {"a": [1,2]} hope that helps') == {"a": [1, 2]}


def test_throttle_lets_first_request_through_and_waits_when_full():
    t = TokenThrottle(1000, completion_allowance=100)
    assert t.wait_for(400) == 0.0          # empty window: never block
    t.record(800)
    assert t.wait_for(400) == 0.0          # 800 + 200 fits
    t.record(200)
    t.window = deque([(ts - 59.6, tok) for ts, tok in t.window])  # pretend a minute has nearly passed
    t0 = time.monotonic()
    waited = t.wait_for(400)
    assert 0.3 <= waited <= 2.0 and time.monotonic() - t0 >= 0.3
    assert len(t.window) == 0              # expired entries were dropped
