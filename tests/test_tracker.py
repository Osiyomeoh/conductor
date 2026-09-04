"""Issue-tracker sync (Linear), offline.

The GraphQL transport is injected, so the mutations are verified without a Linear
workspace, and sync is shown to create one issue per commitment, comment when
work resolves, and do neither on a re-sync.
"""
import json


def test_linear_client_builds_create_and_comment_mutations():
    from conductor.tracker import LinearClient
    calls = []

    def opener(method, url, headers, body):
        calls.append((json.loads(body), headers["Authorization"]))
        if "issueCreate" in json.loads(body)["query"]:
            return 200, json.dumps({"data": {"issueCreate": {"success": True,
                    "issue": {"id": "iss_1", "identifier": "C-1", "url": "u"}}}}).encode()
        return 200, json.dumps({"data": {"commentCreate": {"success": True}}}).encode()

    c = LinearClient(api_key="lin_abc", team_id="team_1", opener=opener)
    issue = c.create_issue("Fix the webhook", "Proof: pytest")
    assert issue["id"] == "iss_1"
    body, auth = calls[0]
    assert auth == "lin_abc"                                   # Linear uses the raw key
    assert body["variables"]["team"] == "team_1"
    assert "issueCreate" in body["query"]

    assert c.comment("iss_1", "verified") is True
    assert "commentCreate" in calls[1][0]["query"]


def test_linear_client_raises_on_errors():
    from conductor.tracker import LinearClient

    def opener(m, u, h, b):
        return 200, json.dumps({"errors": [{"message": "auth"}]}).encode()
    try:
        LinearClient("k", "t", opener=opener).create_issue("x", "y")
        assert False, "expected error"
    except RuntimeError as e:
        assert "linear error" in str(e)


class FakeLinear:
    def __init__(self):
        self.created, self.comments, self._n = [], [], 0

    def create_issue(self, title, desc):
        self._n += 1
        self.created.append(title)
        return {"id": f"iss_{self._n}", "identifier": f"C-{self._n}", "url": "u"}

    def comment(self, issue_id, body):
        self.comments.append((issue_id, body))
        return True


def test_sync_creates_once_and_comments_on_resolution(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/trk-work")
    from conductor.tracker import sync
    from conductor.world import build
    c = build(seed=7)
    c.run(ticks=8)                                   # resolve some commitments
    n = len(list(c.graph))
    fake = FakeLinear()

    r1 = sync(c, fake)
    assert r1["created"] == n                        # one issue per commitment
    assert r1["commented"] >= 1                       # something resolved -> commented
    assert r1["issues"] == n

    r2 = sync(c, fake)                               # re-sync is a no-op
    assert r2["created"] == 0 and r2["commented"] == 0
    assert len(fake.created) == n                    # never duplicated
