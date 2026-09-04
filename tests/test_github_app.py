"""GitHub App auth: mint a real RS256 JWT and exchange it, all offline.

A throwaway RSA key is generated in-test, so the JWT is really signed and really
verified; the installation-token exchange uses an injected transport.
"""
import json
import time

import pytest

from conductor.github import GitHubError


def _keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()).decode()
    pub = key.public_key()
    return pem, pub


def test_mint_jwt_is_signed_and_carries_app_claims():
    import jwt
    from conductor.github_app import mint_jwt
    pem, pub = _keypair()
    token = mint_jwt("123456", pem)
    claims = jwt.decode(token, pub, algorithms=["RS256"])   # real signature check
    assert claims["iss"] == "123456"
    assert claims["iat"] <= int(time.time())
    assert claims["exp"] > int(time.time())


def test_installation_token_hits_the_right_endpoint():
    from conductor.github_app import installation_token
    pem, _ = _keypair()
    calls = []

    def opener(method, url, headers, body):
        calls.append((method, url, headers["Authorization"]))
        return 201, json.dumps({"token": "ghs_installtoken", "expires_at": "2026-01-01T00:00:00Z"}).encode()

    token, exp = installation_token("123456", pem, "42", opener=opener)
    assert token == "ghs_installtoken" and exp.startswith("2026")
    method, url, auth = calls[0]
    assert method == "POST"
    assert url.endswith("/app/installations/42/access_tokens")
    assert auth.startswith("Bearer ")           # the App JWT, not a PAT


def test_installation_token_raises_on_error():
    from conductor.github_app import installation_token
    pem, _ = _keypair()

    def opener(method, url, headers, body):
        return 404, json.dumps({"message": "Not Found"}).encode()

    with pytest.raises(GitHubError) as e:
        installation_token("123456", pem, "42", opener=opener)
    assert e.value.status == 404


def test_client_from_env_prefers_app_then_pat(monkeypatch):
    from conductor import github_app
    pem, _ = _keypair()
    for k in ("CONDUCTOR_GITHUB_TOKEN", "CONDUCTOR_GITHUB_APP_ID",
              "CONDUCTOR_GITHUB_INSTALLATION_ID", "CONDUCTOR_GITHUB_PRIVATE_KEY",
              "CONDUCTOR_GITHUB_PRIVATE_KEY_PATH"):
        monkeypatch.delenv(k, raising=False)

    # No repo -> nothing.
    assert github_app.client_from_env() is None

    # Repo + PAT -> PAT client.
    monkeypatch.setenv("CONDUCTOR_GITHUB_REPO", "acme/app")
    monkeypatch.setenv("CONDUCTOR_GITHUB_TOKEN", "ghp_pat")
    c = github_app.client_from_env()
    assert c is not None and c.token == "ghp_pat"

    # Repo + App creds -> App installation token wins over the PAT.
    monkeypatch.setenv("CONDUCTOR_GITHUB_APP_ID", "123456")
    monkeypatch.setenv("CONDUCTOR_GITHUB_INSTALLATION_ID", "42")
    monkeypatch.setenv("CONDUCTOR_GITHUB_PRIVATE_KEY", pem.replace("\n", "\\n"))

    def opener(method, url, headers, body):
        return 201, json.dumps({"token": "ghs_app", "expires_at": "x"}).encode()

    c = github_app.client_from_env(opener=opener)
    assert c.token == "ghs_app"           # App token, not the PAT
