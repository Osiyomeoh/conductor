"""GitHub integration: verified work becomes a draft pull request.

Phase 1 of the production path. The local executor (execution.py) merges verified
work straight into a local base. Against a real GitHub repo we do not merge for
you: we push the branch, open a DRAFT pull request, and mark it ready for review
only once the evidence has passed. A human still merges. Conductor never
force-pushes and never touches a protected branch directly.

Auth: a token (a fine-grained PAT, or a GitHub App installation token minted
elsewhere). The HTTP layer is injectable so the request shaping is unit-tested
without a network. A GitHub App's JWT->installation-token exchange can wrap this
client later without changing the call sites.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

API = "https://api.github.com"


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"github {status}: {message}")
        self.status = status


@dataclass
class GitHubClient:
    """A thin, typed wrapper over the REST calls Conductor needs. `opener` is the
    callable that performs a request; it defaults to urllib but is injected in
    tests, so every method's URL, verb and body are verifiable offline."""
    token: str
    repo: str                      # "owner/name"
    opener: object = None          # (method, url, headers, body_bytes) -> (status, bytes)

    def _do(self, method: str, path: str, body: dict | None = None) -> dict:
        url = path if path.startswith("http") else f"{API}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "conductor",
        }
        raw = json.dumps(body).encode() if body is not None else None
        if raw is not None:
            headers["Content-Type"] = "application/json"
        status, data = self._transport(method, url, headers, raw)
        if status >= 300:
            msg = ""
            try:
                msg = json.loads(data or b"{}").get("message", "")
            except Exception:  # noqa: BLE001
                msg = (data or b"").decode(errors="replace")[:200]
            raise GitHubError(status, msg)
        return json.loads(data or b"{}") if data else {}

    def _transport(self, method, url, headers, body):
        if self.opener is not None:
            return self.opener(method, url, headers, body)
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    # --- the operations the loop needs ------------------------------------
    def default_branch(self) -> str:
        return self._do("GET", f"/repos/{self.repo}").get("default_branch", "main")

    def branch_sha(self, branch: str) -> str:
        r = self._do("GET", f"/repos/{self.repo}/git/ref/heads/{branch}")
        return r["object"]["sha"]

    def create_branch(self, branch: str, from_sha: str) -> None:
        """Create refs/heads/<branch> at a commit. Idempotent: an existing branch
        is fast-forwarded, never force-moved backward."""
        try:
            self._do("POST", f"/repos/{self.repo}/git/refs",
                     {"ref": f"refs/heads/{branch}", "sha": from_sha})
        except GitHubError as e:
            if e.status == 422:      # already exists
                self._do("PATCH", f"/repos/{self.repo}/git/refs/heads/{branch}",
                         {"sha": from_sha, "force": False})
            else:
                raise

    def open_draft_pr(self, branch: str, base: str, title: str, body: str) -> dict:
        """Open a draft PR from branch into base, or return the existing open one."""
        existing = self._do("GET",
            f"/repos/{self.repo}/pulls?head={self.repo.split('/')[0]}:{branch}&state=open")
        if isinstance(existing, list) and existing:
            return existing[0]
        return self._do("POST", f"/repos/{self.repo}/pulls",
                        {"title": title, "body": body, "head": branch,
                         "base": base, "draft": True})

    def set_check(self, sha: str, name: str, passed: bool, summary: str) -> dict:
        """Record the evidence verdict as a commit status, so it shows on the PR."""
        return self._do("POST", f"/repos/{self.repo}/statuses/{sha}",
                        {"state": "success" if passed else "failure",
                         "context": f"conductor/{name}",
                         "description": summary[:140]})

    def mark_ready(self, pr_number: int) -> dict:
        """Take a draft PR out of draft once its evidence has passed. Conductor
        never merges; a human does."""
        return self._do("PATCH", f"/repos/{self.repo}/pulls/{pr_number}",
                        {"draft": False})

    def pr_reviews(self, pr_number: int) -> list:
        r = self._do("GET", f"/repos/{self.repo}/pulls/{pr_number}/reviews")
        return r if isinstance(r, list) else []


# --- executor: verified work becomes a draft PR ---------------------------
import subprocess  # noqa: E402
from dataclasses import dataclass as _dataclass  # noqa: E402

from .execution import GitExecutor, _git  # noqa: E402


@_dataclass
class GitHubExecutor(GitExecutor):
    """A drop-in for GitExecutor whose repo is a local clone of a GitHub repo.
    Local mechanics (worktrees, checks) are inherited unchanged; the only thing
    that differs is the consequence of a pass: instead of merging locally, push
    the branch and open a draft PR that a human reviews and merges."""
    client: "GitHubClient | None" = None

    def _push(self, branch: str) -> None:
        # Push over an authenticated URL so the token is never persisted in the
        # repo's remote config. Never force.
        owner_repo = self.client.repo
        url = f"https://x-access-token:{self.client.token}@github.com/{owner_repo}.git"
        _git(self.repo, "push", url, f"{branch}:{branch}")

    def merge(self, branch: str) -> tuple[bool, str]:
        """Verified: push the branch, open (or reuse) a draft PR, record the
        passing check on its head commit, and mark it ready for review. Tears
        down the local worktree. A human merges the PR; Conductor never does."""
        if self.client is None:
            return super().merge(branch)          # fall back to local merge
        sha = _git(self.repo, "rev-parse", branch).stdout.strip()
        self._push(branch)
        base = self.client.default_branch()
        pr = self.client.open_draft_pr(branch, base,
                                       title=f"conductor: {branch}",
                                       body="Verified by Conductor. Evidence passed "
                                            "before this was opened for review.")
        self.client.set_check(sha, branch.split("/")[-1], True, "evidence passed")
        if pr.get("number"):
            self.client.mark_ready(int(pr["number"]))
        self.close(branch)
        return True, f"opened PR #{pr.get('number', '?')}"
