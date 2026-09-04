"""Workspace membership: the authority for who may do what in a workspace.

The registry is unit-tested directly, and the endpoints are tested through the
app in enforced-auth mode: the first user bootstraps as admin, an admin adds a
member, a non-admin is refused, and a user who was never added is denied access.
"""
from conductor.membership import Member, MembershipRegistry


def test_registry_add_role_and_remove():
    r = MembershipRegistry()
    assert r.role_of("acme", "u1") is None
    r.add("acme", "u1", "member", email="u1@acme.co", by="admin")
    assert r.role_of("acme", "u1") == "member"
    assert isinstance(r.members("acme")[0], Member)
    assert r.remove("acme", "u1") is True
    assert r.role_of("acme", "u1") is None


def test_registry_rejects_unknown_role():
    r = MembershipRegistry()
    try:
        r.add("acme", "u1", "superuser")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_ensure_owner_bootstraps_first_user_only():
    r = MembershipRegistry()
    assert r.ensure_owner("acme", "founder", "f@acme.co") == "admin"   # empty -> owner
    assert r.ensure_owner("acme", "stranger", "s@x.co") is None        # not a member, no access
    r.add("acme", "stranger", "member")
    assert r.ensure_owner("acme", "stranger") == "member"              # now a member


def _enforced_client(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "1")
    monkeypatch.setenv("CONDUCTOR_SESSION_SECRET", "test-secret")
    memberships._by_tenant.clear()   # fresh membership per test (no reload churn)
    importlib.reload(asgi)
    return TestClient(asgi.app), asgi


def test_membership_endpoints_bootstrap_and_gate(monkeypatch):
    c, asgi = _enforced_client(monkeypatch)
    from conductor.auth import mint_session
    founder = {"authorization": "Bearer " + mint_session("founder", "acme", email="f@acme.co")}
    # First authenticated user of an empty workspace becomes admin (bootstrap).
    who = c.get("/api/whoami", headers=founder).json()
    assert who["roles"] == ["admin"]
    # Admin adds a member.
    r = c.post("/api/members", headers=founder, json={"subject": "ravi", "role": "member", "email": "r@acme.co"})
    assert r.status_code == 200
    assert {m["subject"] for m in r.json()["members"]} == {"founder", "ravi"}
    # The member can read but not add (admin-only), and shows their real role.
    ravi = {"authorization": "Bearer " + mint_session("ravi", "acme")}
    assert c.get("/api/whoami", headers=ravi).json()["roles"] == ["member"]
    assert c.get("/api/members", headers=ravi).status_code == 200
    assert c.post("/api/members", headers=ravi, json={"subject": "x"}).status_code == 403
    # A user who was never added to this workspace is authenticated but denied.
    stranger = {"authorization": "Bearer " + mint_session("stranger", "acme")}
    assert c.get("/api/state", headers=stranger).status_code == 403
    # Admin can remove, but not themselves.
    assert c.request("DELETE", "/api/members/founder", headers=founder).status_code == 400
    assert c.request("DELETE", "/api/members/ravi", headers=founder).status_code == 200
