"""Authentication boundary.

This module does NOT collect passwords or credentials. It verifies a session
that a real identity provider established. Two modes:

  - disabled (default): every request is the demo tenant. This is the hackathon
    prototype behaviour.
  - enforced (CONDUCTOR_REQUIRE_AUTH=1): a request must carry a valid session,
    established by an OIDC/Cognito login flow that runs outside this process.
    The provider issues a signed session token (JWT); we verify it and read the
    tenant and subject from its claims. Wiring the provider's JWKS/issuer is a
    deployment step — the integration points are marked below.

The design keeps credential handling entirely in the identity provider. This
process only ever sees a signed token, never a secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    email: str | None = None


def auth_required() -> bool:
    return os.environ.get("CONDUCTOR_REQUIRE_AUTH", "0") == "1"


# --- session tokens --------------------------------------------------------
# For self-hosted deployments without an external IdP, Conductor can mint its
# own signed session after a login handled elsewhere. HS256 over a server
# secret. For Cognito/Auth0/Okta, replace verify_session with JWKS validation
# (marked below) and keep the same Principal return shape.

def _secret() -> bytes:
    s = os.environ.get("CONDUCTOR_SESSION_SECRET")
    if not s:
        raise RuntimeError(
            "CONDUCTOR_REQUIRE_AUTH=1 needs CONDUCTOR_SESSION_SECRET set to a "
            "strong random value (used to sign session tokens).")
    return s.encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint_session(subject: str, tenant: str, email: str | None = None,
                 ttl_seconds: int = 86400) -> str:
    """Issue a signed session. Call this from your login handler AFTER the
    identity provider has authenticated the user — never from raw credentials
    inside this process."""
    payload = {"sub": subject, "tenant": tenant, "email": email,
               "exp": int(time.time()) + ttl_seconds}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_session(token: str) -> Principal | None:
    """Verify a session token and return its Principal, or None if invalid.

    IdP INTEGRATION POINT: to use Cognito/Auth0/Okta instead of self-minted
    sessions, replace this body with JWKS signature validation against the
    provider's issuer and audience, then map the standard claims (`sub`, a
    tenant/org claim, `email`) onto Principal. The rest of the app is unchanged.
    """
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return Principal(subject=payload["sub"], tenant=payload["tenant"],
                         email=payload.get("email"))
    except Exception:  # noqa: BLE001
        return None


def principal_from(headers, cookies) -> Principal | None:
    """Resolve the caller. Disabled mode returns the demo principal; enforced
    mode requires a valid session in the Authorization bearer or a cookie."""
    if not auth_required():
        return Principal(subject="demo", tenant=os.environ.get("CONDUCTOR_TENANT", "default"))
    token = None
    auth = headers.get("authorization") or headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[7:]
    token = token or cookies.get("conductor_session")
    return verify_session(token) if token else None
