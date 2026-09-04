"""OIDC/SSO token validation, offline.

A real RSA key and JWKS are generated in-test and the provider's endpoints are
injected, so tokens are really signed and really verified against the published
key set, with no network and no live identity provider.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from conductor.auth import Principal
from conductor.oidc import OIDCVerifier

ISS = "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_pool"
AUD = "app-client-123"


def _provider(kid="k1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = kid
    keys = {"keys": [jwk]}

    def fetch(url):
        return {"jwks_uri": ISS + "/.well-known/jwks.json"} if "openid-configuration" in url else keys
    return key, kid, fetch


def _token(key, kid, **claims):
    payload = {"sub": "u1", "iss": ISS, "aud": AUD, "exp": int(time.time()) + 300,
               "email": "a@b.co", **claims}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def test_valid_token_maps_to_principal_with_tenant_and_roles():
    key, kid, fetch = _provider()
    tok = _token(key, kid, **{"custom:tenant": "acme", "cognito:groups": ["admin", "member"]})
    v = OIDCVerifier(issuer=ISS, audience=AUD, fetch=fetch)
    p = v.verify(tok)
    assert isinstance(p, Principal)
    assert p.subject == "u1" and p.tenant == "acme" and p.email == "a@b.co"
    assert "admin" in p.roles and "member" in p.roles


def test_roles_claim_as_space_string():
    key, kid, fetch = _provider()
    tok = _token(key, kid, **{"custom:tenant": "acme", "cognito:groups": "approver member"})
    p = OIDCVerifier(issuer=ISS, audience=AUD, fetch=fetch).verify(tok)
    assert set(p.roles) == {"approver", "member"}


def test_rejects_wrong_issuer_audience_and_expiry():
    key, kid, fetch = _provider()
    v = OIDCVerifier(issuer=ISS, audience=AUD, fetch=fetch)
    assert v.verify(_token(key, kid, iss="https://evil")) is None
    assert v.verify(_token(key, kid, aud="someone-else")) is None
    assert v.verify(_token(key, kid, exp=int(time.time()) - 10)) is None


def test_rejects_token_signed_by_a_different_key():
    key, kid, fetch = _provider()
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"sub": "u1", "iss": ISS, "aud": AUD, "exp": int(time.time()) + 300},
                        other, algorithm="RS256", headers={"kid": kid})
    assert OIDCVerifier(issuer=ISS, audience=AUD, fetch=fetch).verify(forged) is None


def test_rejects_unknown_kid():
    key, _kid, fetch = _provider(kid="k1")
    tok = _token(key, "k1")
    v = OIDCVerifier(issuer=ISS, audience=AUD, fetch=lambda url:
                     ({"jwks_uri": ISS} if "openid" in url else {"keys": []}))
    assert v.verify(tok) is None


def test_audience_optional_when_not_configured():
    key, kid, fetch = _provider()
    tok = _token(key, kid, **{"custom:tenant": "t"})
    p = OIDCVerifier(issuer=ISS, audience=None, fetch=fetch).verify(tok)  # skip aud check
    assert p is not None and p.tenant == "t"


def test_principal_role_check():
    admin = Principal("a", "t", roles=("admin",))
    member = Principal("m", "t", roles=("member",))
    assert admin.has_role("approver") is True          # admin is a superset
    assert member.has_role("approver") is False
    assert member.has_role("member") is True
    assert member.has_role() is True                    # no role required
