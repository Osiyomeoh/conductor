"""The agent marketplace: rated by verified track record, not marketing.

A kind of work with agents on the team carries a real pass rate and job count;
an unproven kind is rated None (honest, not zero); proven kinds rank first.
"""


def test_marketplace_rates_by_track_record(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/mkt-work")
    from conductor.marketplace import listing
    from conductor.world import build
    c = build(seed=7)
    c.run(ticks=8)                                   # agents earn a record
    agents = listing(c)
    kinds = {a["kind"] for a in agents}
    assert {"code", "research", "migration", "review"} <= kinds

    code = next(a for a in agents if a["kind"] == "code")
    assert code["on_team"] is True                    # agent_impl does code
    assert code["verified_jobs"] >= 1                 # it worked during the run
    assert 0.0 <= code["pass_rate"] <= 1.0

    review = next(a for a in agents if a["kind"] == "review")
    assert review["pass_rate"] is None                # nobody does review yet: unproven

    # Proven kinds (a real pass rate) rank before unproven (None).
    proven_flags = [a["pass_rate"] is not None for a in agents]
    assert proven_flags == sorted(proven_flags, reverse=True)


def test_marketplace_endpoint(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/mkt-work2")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    c = TestClient(asgi.app)
    r = c.get("/api/marketplace")
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert len(agents) >= 5 and all("kind" in a and "purpose" in a for a in agents)
