"""Judgment routing: earned expertise per person per domain.

The ledger learns who answers which domain, the domain of a decision is the work
it unblocks, and answering a decision teaches the org — so the next question of
that kind is routed to the person whose judgment it is.
"""
from conductor.routing import ExpertiseLedger, decision_domain


def test_expertise_is_earned_and_best_wins():
    led = ExpertiseLedger()
    led.record("ravi", "code")
    led.record("ravi", "code")
    led.record("sam", "code")
    led.record("sarah", "design")
    assert led.best_for("code") == "ravi"            # most-proven wins
    assert led.best_for("design") == "sarah"
    assert led.best_for("research") is None           # unproven -> nobody
    assert led.best_for("code", candidates={"sam"}) == "sam"   # restricted to a set


def test_decision_domain_is_the_work_it_unblocks():
    class CM:
        def __init__(self, kind):
            self.work_kind = kind

    class Graph:
        def __init__(self, m):
            self.m = m
        def get(self, cid):
            return self.m.get(cid)

    class D:
        blocked = ["a", "b", "c"]

    g = Graph({"a": CM("design"), "b": CM("design"), "c": CM("code")})
    assert decision_domain(g, D()) == "design"        # the dominant kind
    assert decision_domain(Graph({}), D()) == "general"


def test_state_exposes_domain_and_routing(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/route-work")
    from conductor.registry import Registry
    from conductor.server import state
    from conductor.world import persistent
    r = Registry(build_fn=lambda store, tenant: persistent(store=store, tenant=tenant))
    s = r.write("t_route", lambda c: (c.run(ticks=8), state(c))[1])
    assert s["decisions"], "expected a decision to surface"
    d = s["decisions"][0]
    assert "domain" in d and "routed_to" in d
    assert d["routed_to"] is None                     # nobody has earned it yet


def test_answering_teaches_expertise(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/route-work2")
    from conductor.registry import Registry
    from conductor.routing import attach, decision_domain
    from conductor.server import state
    from conductor.world import persistent
    r = Registry(build_fn=lambda store, tenant: persistent(store=store, tenant=tenant))

    def answer_first(c):
        c.run(ticks=8)
        d = list(c.surface.open.values())[0]
        domain = decision_domain(c.graph, d)
        attach(c).record("alex", domain)              # alex answers this domain
        return domain
    domain = r.write("t_route2", answer_first)
    # a later decision of the same domain now routes to alex
    routed = r.read("t_route2", lambda c: attach(c).best_for(domain))
    assert routed == "alex"
