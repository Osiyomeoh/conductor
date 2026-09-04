"""End-to-end: the whole 1000x stack composed as one system.

Unit tests prove the pieces; this proves they work together — a goal derives
work and an outcome, the loop catches lies, a decision routes to a person, the
outcome holds then regresses, and Conductor rolls back and learns. It exists
because composing these features surfaced a real bug (an outcome commitment being
escalated instead of watched) that no single unit test saw.
"""


def test_the_whole_1000x_flow(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/e2e-1000x")
    from conductor.goals import Goal, derive
    from conductor.learning import attach as attach_mem
    from conductor.metrics import MemoryMetricSource
    from conductor.models import EvidenceKind, Status
    from conductor.routing import attach as attach_exp, decision_domain
    from conductor.server import state
    from conductor.world import build

    c = build(seed=7)
    src = MemoryMetricSource()
    c.verifier.metric_source = src
    src.set("onboarding_completion", 0.28)

    # 1. Derive a goal into work + an outcome commitment.
    goal = Goal(intent="cut onboarding drop-off",
                outcome="onboarding_completion >= 0.40", values=["never touch billing"])
    made, _rej, _src = derive(goal, live=False, metric_source=src)
    for cm in made:
        c.graph.add(cm)
    outcome = [cm for cm in made if cm.evidence.kind is EvidenceKind.OUTCOME][0]

    # 2. Run: real work dispatches and lies are caught; the outcome is watched.
    c.run(ticks=10)
    m = state(c)["metrics"]
    assert m["dispatched"] >= 1 and m["claims_rejected"] >= 1
    assert outcome.status is Status.WATCHING          # not dispatched, not escalated

    # 3. Answering a decision routes the domain to that person.
    d = list(c.surface.open.values())[0]
    dom = decision_domain(c.graph, d)
    attach_exp(c).record("sam", dom)
    assert attach_exp(c).best_for(dom) == "sam"

    # 4. Reality hits the target and holds -> the outcome is truly done.
    src.set("onboarding_completion", 0.43)
    c._watch_outcomes(); c._watch_outcomes()
    assert outcome.status is Status.DONE
    assert attach_mem(c).rate("onboarding_completion") == 1.0

    # 5. Reality reverses -> auto-rollback, reopen, and learn from it.
    src.set("onboarding_completion", 0.19)
    c._watch_outcomes()
    assert outcome.status is Status.REJECTED
    assert any("rolled back" in e for e in c.events)
    mem = attach_mem(c).summary()
    assert mem["held"] == 1 and mem["regressed"] == 1     # reality's verdict, both ways
