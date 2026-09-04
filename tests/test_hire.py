"""Hiring an agent from the UI: it joins the roster on probation and can work.

hire_agent is unit-tested (roster member + dispatcher worker + probation), and
the endpoint is tested admin-gated in enforced mode.
"""
import os


def test_hire_agent_adds_roster_member_and_worker(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/hire-work")
    from conductor.world import hire_agent, persistent
    c = persistent(tenant="t_hire")
    before = len(c.dispatcher.workers)
    aid = hire_agent(c, "code")
    assert aid in c.graph.resources                      # on the roster
    assert c.graph.resources[aid].probation is True       # deep-verified until proven
    assert "code" in c.graph.resources[aid].skills
    assert aid in c.dispatcher.workers                    # actually dispatchable
    assert len(c.dispatcher.workers) == before + 1


def test_hire_endpoint_is_admin_gated(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/hire-work")

    # demo mode: admin, hiring works and returns a grown roster.
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    c = TestClient(asgi.app)
    before = len(c.get("/api/team").json()["members"])
    r = c.post("/api/team/hire", json={"kind": "code"})
    assert r.status_code == 200
    assert len(r.json()["members"]) == before + 1
    assert r.post if False else c.post("/api/team/hire", json={}).status_code == 400   # kind required

    # enforced mode: a member cannot hire.
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "1")
    monkeypatch.setenv("CONDUCTOR_SESSION_SECRET", "test-secret")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    c = TestClient(asgi.app)
    from conductor.auth import mint_session
    admin = {"authorization": "Bearer " + mint_session("a", "acme")}
    c.get("/api/whoami", headers=admin)                   # bootstrap admin
    c.post("/api/members", headers=admin, json={"subject": "m", "role": "member"})
    member = {"authorization": "Bearer " + mint_session("m", "acme")}
    assert c.post("/api/team/hire", headers=member, json={"kind": "code"}).status_code == 403
    assert c.post("/api/team/hire", headers=admin, json={"kind": "code"}).status_code == 200
