"""Self-improvement: verified outcomes are the signal the system learns from.

Reality's verdict — did a shipped outcome hold or regress — is recorded per
metric, so Conductor's confidence reflects outcomes, not just check passes.
"""


def test_outcome_memory_rate_and_summary():
    from conductor.learning import OutcomeMemory
    m = OutcomeMemory()
    m.record("signup", True)
    m.record("signup", True)
    m.record("signup", False)
    assert m.rate("signup") == round(2 / 3, 3)
    assert m.rate() == round(2 / 3, 3)
    assert m.rate("unseen") is None
    s = m.summary()
    assert s["held"] == 2 and s["regressed"] == 1 and s["hold_rate"] == round(2 / 3, 3)


def _outcome_conductor(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/learn-work")
    from conductor.metrics import MemoryMetricSource
    from conductor.models import Commitment, Evidence, EvidenceKind, Status
    from conductor.world import build
    c = build(seed=7)
    src = MemoryMetricSource()
    c.verifier.metric_source = src
    cm = Commitment.new("Lift signup", Evidence(EvidenceKind.OUTCOME, spec="signup >= 0.4"))
    cm.status = Status.VERIFYING
    c.graph.add(cm)
    return c, src, cm


def test_watch_records_held_then_regressed(monkeypatch):
    from conductor.learning import attach
    c, src, _cm = _outcome_conductor(monkeypatch)
    src.set("signup", 0.5)
    c._watch_outcomes(); c._watch_outcomes()          # holds -> DONE
    mem = attach(c)
    assert mem.held.get("signup") == 1 and mem.rate("signup") == 1.0

    src.set("signup", 0.2)                            # regresses
    c._watch_outcomes()
    assert mem.regressed.get("signup") == 1
    assert mem.rate("signup") == round(1 / 2, 3)      # one held, one regressed


def test_metrics_endpoint_exposes_hold_rate(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/learn-work2")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    c = TestClient(asgi.app)
    c.post("/api/tick", json={"ticks": 4})
    body = c.get("/api/metrics").text
    assert "conductor_outcome_hold_rate" in body
    assert "conductor_outcomes_held_total" in body
