"""GitHub webhook receiver: the loop hears back when a human acts on a PR.

Signature verification is the security boundary (GitHub cannot send the session
cookie), so it is tested hard. Event handling is tested against a fake conductor,
and the endpoint is tested end to end including the signature gate.
"""
import hashlib
import hmac
import json

from conductor.webhook import handle_event, verify_signature

SECRET = "s3cr3t"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


class FakeConductor:
    def __init__(self, prs):
        self.executor = type("Ex", (), {"prs": prs})()
        self.events = []
    def emit(self, msg):
        self.events.append(msg)


# --- signature -------------------------------------------------------------
def test_signature_valid_and_tamper_rejected():
    body = b'{"hello":"world"}'
    assert verify_signature(SECRET, body, _sign(body)) is True
    assert verify_signature(SECRET, body + b"x", _sign(body)) is False   # body tampered
    assert verify_signature("wrong", body, _sign(body)) is False          # wrong secret
    assert verify_signature(SECRET, body, None) is False                  # no header
    assert verify_signature("", body, _sign(body)) is False               # no secret


# --- event handling --------------------------------------------------------
def test_merged_pr_marks_record_and_emits():
    prs = [{"number": 7, "branch": "conductor/cm_1", "state": "open"}]
    c = FakeConductor(prs)
    out = handle_event("pull_request",
                       {"action": "closed", "pull_request": {"number": 7, "merged": True, "title": "Fix"}}, c)
    assert out == {"handled": True, "event": "merged", "pr": 7}
    assert prs[0]["state"] == "merged"
    assert any("merged PR #7" in e for e in c.events)


def test_closed_without_merge():
    prs = [{"number": 7, "state": "open"}]
    c = FakeConductor(prs)
    out = handle_event("pull_request",
                       {"action": "closed", "pull_request": {"number": 7, "merged": False}}, c)
    assert out["event"] == "closed" and prs[0]["state"] == "closed"


def test_review_approved_and_changes_requested():
    prs = [{"number": 9, "state": "open"}]
    c = FakeConductor(prs)
    handle_event("pull_request_review",
                 {"review": {"state": "approved"}, "pull_request": {"number": 9}}, c)
    assert prs[0]["state"] == "approved" and any("approved PR #9" in e for e in c.events)
    handle_event("pull_request_review",
                 {"review": {"state": "changes_requested"}, "pull_request": {"number": 9}}, c)
    assert prs[0]["state"] == "changes_requested"


def test_ping_and_unknown_are_safe():
    c = FakeConductor([])
    assert handle_event("ping", {}, c)["handled"] is True
    assert handle_event("star", {}, c)["handled"] is False
    assert handle_event("pull_request", {"action": "closed", "pull_request": {"number": 1, "merged": True}}, None)["handled"] is False


# --- endpoint --------------------------------------------------------------
def _app(monkeypatch, secret):
    import importlib, conductor.asgi as asgi
    if secret:
        monkeypatch.setenv("CONDUCTOR_GITHUB_WEBHOOK_SECRET", secret)
    else:
        monkeypatch.delenv("CONDUCTOR_GITHUB_WEBHOOK_SECRET", raising=False)
    importlib.reload(asgi)
    from fastapi.testclient import TestClient
    return TestClient(asgi.app), asgi


def test_endpoint_requires_config_and_valid_signature(monkeypatch):
    c, _ = _app(monkeypatch, secret=None)
    assert c.post("/api/github/webhook", content=b"{}").status_code == 503   # no secret set

    c, asgi = _app(monkeypatch, secret=SECRET)
    body = json.dumps({"action": "closed", "pull_request": {"number": 7, "merged": True}}).encode()
    # bad signature -> 401
    assert c.post("/api/github/webhook", content=body,
                  headers={"x-hub-signature-256": "sha256=deadbeef", "x-github-event": "pull_request"}).status_code == 401
    # valid signature, with a connected repo -> handled
    asgi._gh["c"] = FakeConductor([{"number": 7, "state": "open"}])
    r = c.post("/api/github/webhook", content=body,
               headers={"x-hub-signature-256": _sign(body), "x-github-event": "pull_request"})
    assert r.status_code == 200 and r.json()["event"] == "merged"
