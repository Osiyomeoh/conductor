"""Goal-to-plan derivation: set a goal, get work + an outcome commitment.

Deriving a goal produces the work believed to move the metric, plus the goal's
metric itself as an OUTCOME commitment that is only done when reality moves.
"""
from conductor.goals import Goal, derive
from conductor.metrics import MemoryMetricSource
from conductor.models import EvidenceKind


def test_derive_appends_the_outcome_commitment():
    src = MemoryMetricSource()
    src.set("onboarding", 0.30)
    goal = Goal(intent="cut onboarding drop-off",
                outcome="onboarding >= 0.40", values=["never touch billing", "bias reversible"])
    made, _rejected, _source = derive(goal, live=False, metric_source=src)

    outcomes = [c for c in made if c.evidence.kind is EvidenceKind.OUTCOME]
    assert len(outcomes) == 1
    assert outcomes[0].evidence.spec == "onboarding >= 0.40"
    assert outcomes[0].consequential is False         # reality confirms it, not a person/worker
    assert len(made) >= 2                              # work commitments + the outcome


def test_derive_without_outcome_is_just_work():
    made, _r, _s = derive(Goal(intent="tidy the onboarding code"), live=False)
    assert all(c.evidence.kind is not EvidenceKind.OUTCOME for c in made)


def test_goal_endpoint_materializes(monkeypatch):
    import importlib, conductor.asgi as asgi
    from conductor.membership import memberships
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/goal-work")
    memberships._by_tenant.clear()
    importlib.reload(asgi)
    c = TestClient(asgi.app)
    r = c.post("/api/goal", json={"intent": "lift activation",
                                  "outcome": "activation >= 0.5", "values": ["bias reversible"]})
    assert r.status_code == 200
    body = r.json()
    assert body["derived"] >= 2
    # the outcome commitment is on the board, watching (no metric source in the demo)
    assert any("Reach the goal" in x["title"] for x in body["board"])
