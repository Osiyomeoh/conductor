"""OIDC / SSO token validation.

The production sign-in: an identity provider (Cognito, Auth0, Okta, Google)
authenticates the user and issues a signed JWT. Conductor never sees a password;
it verifies the token's RS256 signature against the provider's published JWKS,
checks the issuer, audience and expiry, and maps the claims onto a Principal
(subject, tenant/org, email, roles). Turned on by setting CONDUCTOR_OIDC_ISSUER.

The key resolution is injectable, so validation is unit-tested against a locally
generated key and JWKS with no network and no live provider.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

from .auth import Principal


class OIDCVerifier:
    def __init__(self, issuer: str, audience: str | None = None,
                 tenant_claim: str = "custom:tenant", roles_claim: str = "cognito:groups",
                 jwks: dict | None = None, fetch=None):
        self.issuer = issuer.rstrip("/")
        self.audience = audience or None
        self.tenant_claim = tenant_claim
        self.roles_claim = roles_claim
        self._jwks = jwks                       # {kid: jwk} or None to fetch
        self._fetch = fetch or self._http_get
        self._cached_at = 0.0 if jwks is None else time.time()

    def _http_get(self, url: str) -> dict:
        with urllib.request.urlopen(url, timeout=10) as r:   # noqa: S310
            return json.loads(r.read())

    def _jwks_uri(self) -> str:
        conf = self._fetch(f"{self.issuer}/.well-known/openid-configuration")
        return conf["jwks_uri"]

    def _keys(self, force: bool = False) -> dict:
        if self._jwks is not None and not force and (time.time() - self._cached_at) < 3600:
            return self._jwks
        data = self._fetch(self._jwks_uri())
        self._jwks = {k["kid"]: k for k in data.get("keys", []) if "kid" in k}
        self._cached_at = time.time()
        return self._jwks

    def verify(self, token: str) -> Principal | None:
        """Validate the token and return a Principal, or None if it is invalid,
        expired, or signed by a key the provider does not publish."""
        import jwt
        from jwt.algorithms import RSAAlgorithm
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            jwk = self._keys().get(kid) or self._keys(force=True).get(kid)   # refresh on rotation
            if jwk is None:
                return None
            key = RSAAlgorithm.from_jwk(json.dumps(jwk))
            opts = {"verify_aud": self.audience is not None}
            claims = jwt.decode(token, key, algorithms=["RS256"], issuer=self.issuer,
                                audience=self.audience, options=opts)
        except Exception:  # noqa: BLE001
            return None
        roles = claims.get(self.roles_claim) or claims.get("roles") or []
        if isinstance(roles, str):
            roles = [r for r in roles.replace(",", " ").split() if r]
        tenant = (claims.get(self.tenant_claim) or claims.get("org")
                  or os.environ.get("CONDUCTOR_TENANT", "default"))
        return Principal(subject=claims.get("sub", ""), tenant=str(tenant),
                         email=claims.get("email"), roles=tuple(roles))


_verifier: OIDCVerifier | None = None


def verifier_from_env() -> OIDCVerifier | None:
    """A process-wide verifier built from the environment, or None when SSO is
    not configured. Cached so JWKS are fetched once, not per request."""
    global _verifier
    issuer = os.environ.get("CONDUCTOR_OIDC_ISSUER")
    if not issuer:
        return None
    if _verifier is None or _verifier.issuer != issuer.rstrip("/"):
        _verifier = OIDCVerifier(
            issuer=issuer,
            audience=os.environ.get("CONDUCTOR_OIDC_AUDIENCE"),
            tenant_claim=os.environ.get("CONDUCTOR_OIDC_TENANT_CLAIM", "custom:tenant"),
            roles_claim=os.environ.get("CONDUCTOR_OIDC_ROLES_CLAIM", "cognito:groups"))
    return _verifier
