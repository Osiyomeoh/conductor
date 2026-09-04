"""GitHub App authentication.

A GitHub App is the production identity: users install it on their repos, and it
acts as its own bot with short-lived, per-installation tokens rather than a
personal token that acts as a human. The flow is two hops:

  1. Sign a short (10 min) RS256 JWT with the App's private key, proving "I am
     App <id>".
  2. Exchange that JWT for an installation access token (~1 hour) scoped to one
     installation.

That installation token is then handed to the ordinary GitHubClient, so nothing
downstream changes: the App is a drop-in source of the same bearer token a PAT
provides. The HTTP layer is injectable, so the exchange is unit-tested offline.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .github import API, GitHubClient, GitHubError


def mint_jwt(app_id: str, private_key_pem: str) -> str:
    """A short-lived RS256 JWT that authenticates as the App itself."""
    import jwt
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": str(app_id)}
    token = jwt.encode(payload, private_key_pem, algorithm="RS256")
    return token if isinstance(token, str) else token.decode()


def _post(url: str, bearer: str, opener=None) -> tuple[int, bytes]:
    headers = {"Authorization": f"Bearer {bearer}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "conductor"}
    if opener is not None:
        return opener("POST", url, headers, b"")
    req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def installation_token(app_id: str, private_key_pem: str, installation_id: str,
                       opener=None) -> tuple[str, str]:
    """Exchange an App JWT for an installation access token. Returns
    (token, expires_at). The token is short-lived; mint a fresh one per session."""
    jwt_token = mint_jwt(app_id, private_key_pem)
    url = f"{API}/app/installations/{installation_id}/access_tokens"
    status, data = _post(url, jwt_token, opener=opener)
    if status >= 300:
        msg = ""
        try:
            msg = json.loads(data or b"{}").get("message", "")
        except Exception:  # noqa: BLE001
            msg = (data or b"").decode(errors="replace")[:200]
        raise GitHubError(status, msg or "installation token exchange failed")
    body = json.loads(data or b"{}")
    return body["token"], body.get("expires_at", "")


def _private_key_from_env() -> str | None:
    """The App private key, either inline (PEM, with \\n escapes tolerated) or a
    path. A key never belongs in the repo, so this only reads the environment."""
    inline = os.environ.get("CONDUCTOR_GITHUB_PRIVATE_KEY")
    if inline:
        return inline.replace("\\n", "\n")
    path = os.environ.get("CONDUCTOR_GITHUB_PRIVATE_KEY_PATH")
    if path and os.path.isfile(path):
        with open(path) as f:
            return f.read()
    return None


def client_from_env(opener=None) -> "GitHubClient | None":
    """Build a GitHubClient from the environment, preferring a GitHub App
    installation (production) and falling back to a PAT (the fast path). Returns
    None when neither is configured."""
    repo = os.environ.get("CONDUCTOR_GITHUB_REPO")
    if not repo:
        return None
    app_id = os.environ.get("CONDUCTOR_GITHUB_APP_ID")
    install = os.environ.get("CONDUCTOR_GITHUB_INSTALLATION_ID")
    key = _private_key_from_env()
    if app_id and install and key:
        token, _exp = installation_token(app_id, key, install, opener=opener)
        return GitHubClient(token=token, repo=repo)
    pat = os.environ.get("CONDUCTOR_GITHUB_TOKEN")
    return GitHubClient(token=pat, repo=repo) if pat else None
