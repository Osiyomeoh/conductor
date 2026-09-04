"""Cost governance and observability.

At or over the spend ceiling, ready work is held rather than dispatched, so a
runaway can only ever cost up to the ceiling. The metrics endpoint exposes the
operational numbers in Prometheus format for a scrape and for alarms.
"""
import types


def test_cost_ceiling_holds_ready_work(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/cc-work")
    from conductor.models import Status
    from conductor.world import build
    c = build(seed=7)
    c.cost_ceiling = 1.0
    c.cost = types.SimpleNamespace(total=999.0)      # already over the ceiling
    ready_before = len(list(c.graph.ready()))
    assert ready_before > 0
    c._dispatch()
    assert c.metrics.dispatched == 0                 # nothing dispatched over budget
    assert c.metrics.held >= ready_before            # all held instead
    assert any(cm.status is Status.HELD and "ceiling" in cm.history[-1]
               for cm in c.graph)


def test_below_ceiling_still_dispatches(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/cc-work2")
    from conductor.world import build
    c = build(seed=7)
    c.cost_ceiling = 1000.0
    c.cost = types.SimpleNamespace(total=0.0)
    c._dispatch()
    assert c.metrics.dispatched > 0                  # under budget, work flows


def test_metrics_endpoint_is_prometheus(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/cc-work3")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    c = TestClient(asgi.app)
    c.post("/api/tick", json={"ticks": 8})           # generate some activity
    r = c.get("/api/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    for name in ("conductor_verified_total", "conductor_claims_caught_total",
                 "conductor_catch_rate", "conductor_held", "conductor_spend_usd",
                 "conductor_active_boards"):
        assert name in body
    # counters are integers, gauges present; the format parses as "name value"
    for line in body.splitlines():
        if line and not line.startswith("#"):
            assert len(line.split()) == 2
