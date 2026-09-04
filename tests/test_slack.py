"""Slack delivery and the interactive answer path, offline.

Signature verification is the security boundary and is tested hard; message
shaping and action parsing are pure; and the interactive endpoint is driven end
to end with a correctly signed payload that answers a real decision.
"""
import hashlib
import hmac
import json
import time
import urllib.parse

from conductor.slack import (SlackClient, decision_blocks, parse_action,
                             verify_signature)

SECRET = "shhh"


def _sign(ts: str, body: bytes) -> str:
    base = f"v0:{ts}:{body.decode()}".encode()
    return "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()


def test_signature_valid_stale_and_tampered():
    ts = str(int(time.time()))
    body = b"payload=%7B%7D"
    assert verify_signature(SECRET, ts, body, _sign(ts, body)) is True
    assert verify_signature(SECRET, ts, body + b"x", _sign(ts, body)) is False   # tampered
    assert verify_signature("wrong", ts, body, _sign(ts, body)) is False          # wrong secret
    old = str(int(time.time()) - 10000)
    assert verify_signature(SECRET, old, body, _sign(old, body)) is False          # replay/stale
    assert verify_signature(SECRET, ts, body, None) is False                       # no signature


def test_decision_blocks_and_action_roundtrip():
    d = {"id": "dec_1", "question": "Paywall position?", "commitments": 4,
         "review_minutes": 90, "options": ["after value", "on signup"]}
    blocks = decision_blocks(d)
    btns = blocks[1]["elements"]
    assert [b["text"]["text"] for b in btns] == ["after value", "on signup"]
    # the value carries id|choice, which parse_action reads back
    payload = {"actions": [{"value": btns[0]["value"], "action_id": "answer_0"}]}
    assert parse_action(payload) == ("dec_1", "after value")
    assert parse_action({"actions": [{"value": "no-pipe"}]}) is None


def test_slack_client_posts_via_injected_transport():
    seen = {}

    def opener(method, url, headers, body):
        seen["url"] = url
        seen["body"] = json.loads(body)
        seen["auth"] = headers["Authorization"]
        return 200, json.dumps({"ok": True, "ts": "1.2"}).encode()

    c = SlackClient(token="xoxb-1", opener=opener)
    c.post_decision("#eng", {"id": "d1", "question": "Q?", "options": ["a", "b"]})
    assert seen["url"].endswith("/chat.postMessage")
    assert seen["body"]["channel"] == "#eng" and seen["auth"] == "Bearer xoxb-1"
    assert seen["body"]["blocks"][1]["elements"][0]["value"] == "d1|a"


def test_slack_client_raises_on_error():
    def opener(m, u, h, b):
        return 200, json.dumps({"ok": False, "error": "channel_not_found"}).encode()
    try:
        SlackClient(token="x", opener=opener).post_text("#no", "hi")
        assert False, "expected error"
    except RuntimeError as e:
        assert "channel_not_found" in str(e)


def _client(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    return TestClient(asgi.app), asgi


def test_interactive_endpoint_answers_a_real_decision(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_SLACK_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CONDUCTOR_SLACK_TENANT", "default")
    c, _ = _client(monkeypatch)

    # Surface a decision on the "default" tenant and grab its id.
    st = c.post("/api/tick", json={"ticks": 8}).json()
    # the interactive tenant is "default"; make sure it has a decision by ticking it
    import conductor.asgi as asgi
    decisions = asgi.registry.read("default", asgi.state).get("decisions", [])
    if not decisions:
        asgi.registry.write("default", lambda cc: cc.run(ticks=8))
        decisions = asgi.registry.read("default", asgi.state).get("decisions", [])
    did = decisions[0]["id"]
    choice = decisions[0]["options"][0]

    payload = {"actions": [{"value": f"{did}|{choice}", "action_id": "answer_0"}]}
    body = urllib.parse.urlencode({"payload": json.dumps(payload)}).encode()
    ts = str(int(time.time()))
    # unsigned -> 401
    assert c.post("/api/slack/interactive", content=body,
                  headers={"x-slack-request-timestamp": ts, "x-slack-signature": "v0=bad"}).status_code == 401
    # signed -> answered
    r = c.post("/api/slack/interactive", content=body,
               headers={"x-slack-request-timestamp": ts, "x-slack-signature": _sign(ts, body)})
    assert r.status_code == 200 and "Answered" in r.json()["text"]
    # the decision is now gone from the surface
    left = [d["id"] for d in asgi.registry.read("default", asgi.state)["decisions"]]
    assert did not in left


def test_interactive_requires_config(monkeypatch):
    monkeypatch.delenv("CONDUCTOR_SLACK_SIGNING_SECRET", raising=False)
    c, _ = _client(monkeypatch)
    assert c.post("/api/slack/interactive", content=b"payload=%7B%7D").status_code == 503
