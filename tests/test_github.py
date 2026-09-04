"""GitHub client: verify request shaping and verdict mapping without a network.

The transport is injected, so each method's verb, URL and body are asserted
against canned responses. This is what lets the integration be built and trusted
before a real GitHub App is registered.
"""
import json

from conductor.github import GitHubClient, GitHubError


class FakeGitHub:
    """Records requests and replays queued responses. A response is
    (status, dict-or-list); the body is JSON-encoded for the client to parse."""
    def __init__(self):
        self.calls = []
        self._queue = []

    def enqueue(self, status, payload):
        self._queue.append((status, json.dumps(payload).encode()))
        return self

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url,
                           "body": json.loads(body) if body else None,
                           "auth": headers.get("Authorization")})
        return self._queue.pop(0)


def client(fake):
    return GitHubClient(token="t0ken", repo="acme/app", opener=fake)


def test_create_branch_posts_ref_and_sends_auth():
    fake = FakeGitHub().enqueue(201, {"ref": "refs/heads/x"})
    client(fake).create_branch("conductor/cm_1", "abc123")
    call = fake.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/repos/acme/app/git/refs")
    assert call["body"] == {"ref": "refs/heads/conductor/cm_1", "sha": "abc123"}
    assert call["auth"] == "Bearer t0ken"


def test_create_branch_existing_falls_back_to_patch():
    fake = FakeGitHub().enqueue(422, {"message": "Reference already exists"}) \
                       .enqueue(200, {"ref": "refs/heads/x"})
    client(fake).create_branch("conductor/cm_1", "def456")
    assert fake.calls[0]["method"] == "POST"        # tried to create
    assert fake.calls[1]["method"] == "PATCH"        # then updated the ref
    assert fake.calls[1]["body"]["force"] is False    # never a force-move


def test_open_draft_pr_reuses_existing_open_pr():
    fake = FakeGitHub().enqueue(200, [{"number": 7, "draft": True}])
    pr = client(fake).open_draft_pr("conductor/cm_1", "main", "t", "b")
    assert pr["number"] == 7
    assert len(fake.calls) == 1 and fake.calls[0]["method"] == "GET"   # no POST


def test_open_draft_pr_creates_when_none_exists():
    fake = FakeGitHub().enqueue(200, []).enqueue(201, {"number": 9, "draft": True})
    pr = client(fake).open_draft_pr("conductor/cm_1", "main", "Fix webhook", "body")
    assert pr["number"] == 9
    post = fake.calls[1]
    assert post["method"] == "POST" and post["url"].endswith("/repos/acme/app/pulls")
    assert post["body"]["draft"] is True and post["body"]["base"] == "main"


def test_set_check_maps_verdict_to_status_state():
    fake = FakeGitHub().enqueue(201, {}).enqueue(201, {})
    c = client(fake)
    c.set_check("sha1", "cm_1", True, "assert passed")
    c.set_check("sha1", "cm_1", False, "assert failed: not lowercased")
    assert fake.calls[0]["body"]["state"] == "success"
    assert fake.calls[1]["body"]["state"] == "failure"
    assert fake.calls[1]["body"]["context"] == "conductor/cm_1"


def test_mark_ready_clears_draft():
    fake = FakeGitHub().enqueue(200, {"number": 9, "draft": False})
    client(fake).mark_ready(9)
    assert fake.calls[0]["method"] == "PATCH"
    assert fake.calls[0]["body"] == {"draft": False}


def test_http_error_raises_githuberror_with_status():
    fake = FakeGitHub().enqueue(403, {"message": "Resource not accessible"})
    try:
        client(fake).default_branch()
        assert False, "expected GitHubError"
    except GitHubError as e:
        assert e.status == 403 and "not accessible" in str(e)


def test_executor_merge_opens_draft_pr_and_marks_ready(tmp_path, monkeypatch):
    """On verified work the GitHub executor pushes the branch, opens a draft PR,
    records the passing check, and takes it out of draft. It never merges."""
    import subprocess
    from conductor.github import GitHubExecutor

    repo = str(tmp_path)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", repo, *args], check=True)
    (tmp_path / "README.md").write_text("# base\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "base"], check=True)
    subprocess.run(["git", "-C", repo, "branch", "conductor/cm_1"], check=True)

    fake = (FakeGitHub()
            .enqueue(200, {"default_branch": "main"})     # default_branch()
            .enqueue(200, [])                              # open_draft_pr: none open
            .enqueue(201, {"number": 12, "draft": True})  # create draft PR
            .enqueue(201, {}))                            # set_check
    ex = GitHubExecutor(repo=repo, client=client(fake))
    monkeypatch.setattr(ex, "_push", lambda branch: None)   # no network in tests

    ok, detail = ex.merge("conductor/cm_1")
    assert ok and "PR #12" in detail
    assert any(c["method"] == "POST" and c["url"].endswith("/pulls") for c in fake.calls)   # opened PR
    assert any(c["body"].get("draft") is True for c in fake.calls if c["method"] == "POST" and c["url"].endswith("/pulls"))  # as a draft
    assert any(c["body"].get("state") == "success" for c in fake.calls if c["method"] == "POST" and "statuses" in c["url"])
    assert not any(c["method"] == "PATCH" for c in fake.calls)   # never force-promotes; the human does


def test_build_for_github_wires_the_pr_executor(tmp_path):
    """The connect flow clones (injected here) and hands the loop a Conductor
    whose executor is the GitHub draft-PR executor carrying the client."""
    import subprocess
    from conductor.github import GitHubClient, GitHubExecutor, build_for_github

    def fake_clone(client, dest):
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", dest, *args], check=True)
        (tmp_path / "README.md").write_text("# x\n")
        subprocess.run(["git", "-C", dest, "add", "-A"], check=True)
        subprocess.run(["git", "-C", dest, "commit", "-q", "-m", "base"], check=True)
        return dest

    client = GitHubClient(token="t", repo="acme/app", opener=FakeGitHub())
    c = build_for_github(client, str(tmp_path), cloner=fake_clone)
    assert isinstance(c.executor, GitHubExecutor)
    assert c.executor.client is client


def _api_client(monkeypatch, allow_repo, token):
    import importlib, conductor.asgi as asgi
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    if allow_repo:
        monkeypatch.setenv("CONDUCTOR_ALLOW_REPO", "1")
    else:
        monkeypatch.delenv("CONDUCTOR_ALLOW_REPO", raising=False)
    if token:
        monkeypatch.setenv("CONDUCTOR_GITHUB_TOKEN", token)
        monkeypatch.setenv("CONDUCTOR_GITHUB_REPO", "acme/app")
    else:
        monkeypatch.delenv("CONDUCTOR_GITHUB_TOKEN", raising=False)
    importlib.reload(asgi)
    return TestClient(asgi.app)


def test_github_connect_is_gated(monkeypatch):
    # disabled -> 403; enabled but no token -> 400
    c = _api_client(monkeypatch, allow_repo=False, token=None)
    assert c.get("/api/github").json()["enabled"] is False
    assert c.post("/api/github/connect").status_code == 403

    c = _api_client(monkeypatch, allow_repo=True, token=None)
    s = c.get("/api/github").json()
    assert s["enabled"] is True and s["configured"] is False
    assert c.post("/api/github/connect").status_code == 400

    c = _api_client(monkeypatch, allow_repo=True, token="ghp_x")
    s = c.get("/api/github").json()
    assert s["configured"] is True and s["repo_name"] == "acme/app" and s["connected"] is False
