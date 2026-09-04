"""The invariants.

These are not coverage tests. Each one pins a property that, if it broke,
would quietly turn Conductor back into the thing it exists to replace: a
tracker that believes what workers tell it.

Several are regressions for bugs found by running the system, and the comment
on each says which failure it is guarding against.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from conductor.attention import AttentionBudget
from conductor.cost import CostLedger
from conductor.decisions import DecisionSurface
from conductor.graph import CommitmentGraph
from conductor.models import (Action, Commitment, Decision, Evidence, EvidenceKind,
                              Resource, ResourceType, Status, now)
from conductor.policy import PolicyEngine
from conductor.roster import AgentSpec, Roster
from conductor.trust import TrustLedger
from conductor.verification import VerificationRunner, evidence_quality
from conductor.world import build


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def cm(title="t", kind=EvidenceKind.COMMAND, spec="true", **kw):
    return Commitment.new(title, Evidence(kind, spec=spec), **kw)


# --- done is a claim, not a fact -------------------------------------------

def test_evidence_none_fails_closed(workdir):
    """A commitment with no proof is a planning defect, not a free pass. If
    this ever returns True, every unverifiable task silently becomes done."""
    c = cm(kind=EvidenceKind.NONE, spec="")
    assert VerificationRunner(workdir).verify(c) is False
    assert c.status is Status.REJECTED


def test_failing_command_rejects(workdir):
    c = cm(spec="exit 1")
    assert VerificationRunner(workdir).verify(c) is False
    assert c.status is Status.REJECTED


def test_passing_command_completes(workdir):
    open(os.path.join(workdir, "a.txt"), "w").write("TOKEN\n")
    c = cm(spec="grep -q TOKEN a.txt")
    assert VerificationRunner(workdir).verify(c) is True
    assert c.status is Status.DONE


def test_trivial_evidence_is_refused_at_plan_time():
    """A check that cannot fail launders a false claim into a green tick."""
    for spec in ("true", ":", "echo ok"):
        ok, _ = evidence_quality(Evidence(EvidenceKind.COMMAND, spec=spec))
        assert ok is False
    ok, _ = evidence_quality(Evidence(EvidenceKind.COMMAND, spec="pytest -q"))
    assert ok is True


def test_human_review_never_auto_passes(workdir):
    c = cm(kind=EvidenceKind.HUMAN_REVIEW, spec="")
    assert VerificationRunner(workdir).verify(c) is not True
    assert c.status is not Status.DONE


# --- attention is the constraint -------------------------------------------

def test_budget_holds_what_it_cannot_absorb():
    b = AttentionBudget("sam", minutes_per_day=30)
    c = cm(review_cost_minutes=45)
    assert b.can_absorb(c) is False
    b.hold(c)
    assert c.status is Status.HELD
    assert "45m" in c.history[-1] or "30m" in c.history[-1]


def test_rejected_work_costs_the_reviewer_nothing():
    """The core promise: a human never pays attention for work that failed."""
    b = AttentionBudget("sam", minutes_per_day=60)
    c = cm(review_cost_minutes=20)
    b.reserve(c)
    b.release(c, consumed=False)
    assert b.spent == 0
    assert b.remaining == 60


# --- trust is earned slowly and lost at once -------------------------------

def test_trust_falls_immediately_and_deepens_the_check():
    t = TrustLedger()
    for _ in range(10):
        t.record("w", "code", True)
    assert t.evidence_depth("w", "code") == "light"
    t.record("w", "code", False)
    assert t.evidence_depth("w", "code") != "light"


def test_peek_does_not_create_records():
    """Ranking workers must not write. This bug produced phantom trust rows
    for people who had never done that kind of work."""
    t = TrustLedger()
    t.peek("someone", "code")
    assert t.records == {}


# --- the gate ---------------------------------------------------------------

@pytest.mark.parametrize("flag", ["touches_production", "touches_money",
                                  "speaks_to_customer"])
def test_hard_blocks_survive_full_autonomy(flag):
    """No autonomy setting may unlock these. If one ever does, the system is
    no longer safe to leave running."""
    p = PolicyEngine(autonomy=1.0)
    v = p.evaluate(Action(kind="dispatch", commitment_id=None, summary="x",
                          payload={flag: True}))
    assert v.decision is Decision.BLOCK


# --- the roster -------------------------------------------------------------

def _graph_with_human():
    g = CommitmentGraph()
    g.add_resource(Resource("human_sam", ResourceType.HUMAN, "Sam",
                            scopes=["repo:read", "repo:write:branch"]))
    return g


def test_delegate_cannot_exceed_its_principal():
    g = _graph_with_human()
    r = Roster(graph=g, trust=TrustLedger())
    a = r.hire("a1", "delegate", AgentSpec(purpose="p", work_kinds=["code"],
                                           scopes=["repo:read", "prod:deploy"]),
               principal="human_sam")
    assert "prod:deploy" not in a.scopes


def test_delegated_work_is_reviewed_by_the_principal():
    g = _graph_with_human()
    r = Roster(graph=g, trust=TrustLedger())
    r.hire("a1", "delegate", AgentSpec(purpose="p", work_kinds=["code"]),
           principal="human_sam")
    assert r.reviewer_for("a1") == "human_sam"


def test_new_agents_start_on_probation():
    g = _graph_with_human()
    r = Roster(graph=g, trust=TrustLedger())
    a = r.hire("a1", "x", AgentSpec(purpose="p", work_kinds=["code"]))
    assert a.probation is True
    assert r.graduate("a1") is False


def test_judgment_work_is_never_a_hiring_signal():
    """Regression: the roster proposed hiring a 'product agent' to take over
    the paywall decision. Automating judgment is the exact failure this
    product exists to prevent."""
    g = _graph_with_human()
    for _ in range(5):
        c = cm(kind=EvidenceKind.HUMAN_REVIEW, spec="", ambiguous=True)
        c.work_kind = "product"
        g.add(c)
    r = Roster(graph=g, trust=TrustLedger())
    assert r.bottlenecks(min_waiting=1) == []


# --- decisions --------------------------------------------------------------

def test_same_uncertainty_compresses_to_one_question():
    s = DecisionSurface()
    d1 = s.raise_question("a?", ["x", "y"], "key:1", "cm1")
    d2 = s.raise_question("b?", ["x", "y"], "key:1", "cm2")
    assert d1.id == d2.id
    assert len(s.open) == 1
    assert set(d1.blocked) == {"cm1", "cm2"}


def test_questions_rank_by_what_they_unblock():
    s = DecisionSurface()
    s.raise_question("small?", ["x", "y"], "k1", "cm1")
    s.raise_question("big?", ["x", "y"], "k2", "cm2")
    s.raise_question("big?", ["x", "y"], "k2", "cm3")
    assert s.queue()[0].uncertainty_key == "k2"


# --- cost -------------------------------------------------------------------

def test_discard_overrides_verified_spend():
    """Regression: work on a losing branch often passes its check, but nobody
    will ever use it. Reporting that as verified spend flatters the one number
    that has to be honest."""
    led = CostLedger()
    c = cm()
    led.record(c, "w", "default", 1000, 1000)
    led.settle(c.id, "verified")
    led.settle(c.id, "discarded")
    assert led.by_outcome().get("verified", 0) == 0
    assert led.by_outcome()["discarded"] > 0


# --- the loop ---------------------------------------------------------------

def test_answering_a_judgment_call_completes_it():
    """Regression: an answered decision went back to `pending`, was
    re-escalated on the next tick, and looped forever."""
    c = build()
    c.run(ticks=4)
    q = [d for d in c.surface.queue() if len(d.options) >= 2]
    assert q, "expected at least one answerable question"
    d = q[0]
    target = c.graph.get(d.blocked[0])
    c.answer(d.id, d.options[0])
    c.run(ticks=3)
    assert target.status is Status.DONE
    assert d.id not in c.surface.open


def test_speculation_needs_real_options():
    """Regression: with no options declared the loop invented 'option A' and
    then spent real money building it."""
    c = build()
    c.run(ticks=4)
    for d in c.surface.queue():
        if len(d.options) < 2:
            assert not [b for b in c.speculation.branches.values()
                        if b.decision_id == d.id]


def test_nothing_reaches_done_without_passing_evidence():
    """The whole product, as one assertion."""
    c = build()
    c.run(ticks=8)
    for x in c.graph:
        if x.status is Status.DONE:
            assert x.evidence.passed is True, f"{x.title} is done without proof"


# --- persistence ------------------------------------------------------------

def test_replay_reconstructs_the_run_exactly(tmp_path):
    """The state IS the log. If a rebuilt graph disagrees with the live one,
    the loop cannot be resumed and a run cannot be audited."""
    from conductor.events import JsonlStore
    from conductor.graph import CommitmentGraph
    from conductor.replay import rebuild

    log = str(tmp_path / "c.jsonl")
    c = build(store=JsonlStore(log))
    c.run(ticks=6)
    q = [d for d in c.surface.queue() if len(d.options) >= 2]
    if q:
        c.answer(q[0].id, q[0].options[0])
        c.run(ticks=6)

    live = {x.id: x.status for x in c.graph}
    fresh = CommitmentGraph()
    rebuild(fresh, JsonlStore(log).read())
    assert {x.id: x.status for x in fresh} == live


def test_replay_does_not_re_record(tmp_path):
    """Replaying facts must rebuild history, not duplicate it."""
    from conductor.events import JsonlStore

    log = str(tmp_path / "c.jsonl")
    c = build(store=JsonlStore(log))
    c.run(ticks=4)
    before = sum(1 for _ in open(log))
    c.resume()
    assert sum(1 for _ in open(log)) == before


def test_tenants_are_isolated(tmp_path):
    """One log, many teams. A tenant must never see another's work."""
    from conductor.events import EventKind, JsonlStore, Recorder

    store = JsonlStore(str(tmp_path / "c.jsonl"))
    a, b = Recorder(store, "team_a"), Recorder(store, "team_b")
    a.record(EventKind.PLANNED, commitment_id="cm_a")
    b.record(EventKind.PLANNED, commitment_id="cm_b")
    assert [e.commitment_id for e in a.history()] == ["cm_a"]
    assert [e.commitment_id for e in b.history()] == ["cm_b"]


def test_sequence_continues_across_restarts(tmp_path):
    """A resumed recorder must not reuse sequence numbers already on disk."""
    from conductor.events import EventKind, JsonlStore, Recorder

    path = str(tmp_path / "c.jsonl")
    r1 = Recorder(JsonlStore(path))
    for _ in range(3):
        r1.record(EventKind.PLANNED, commitment_id="x")
    r2 = Recorder(JsonlStore(path))
    e = r2.record(EventKind.DISPATCHED, commitment_id="x")
    assert e.seq == 4


def test_review_cost_does_not_compound_across_retries():
    """Regression: the trust multiplier scaled the LAST value rather than the
    planner's estimate, so a repeatedly deep-verified item went 40 -> 80 -> 640
    and starved the reviewer's budget on its own."""
    from conductor.dispatcher import Dispatcher
    from conductor.policy import PolicyEngine

    g = CommitmentGraph()
    g.add_resource(Resource("a1", ResourceType.AGENT, "a", skills=["code"]))
    g.add_resource(Resource("h1", ResourceType.HUMAN, "h"))
    t = TrustLedger()
    for _ in range(3):
        t.record("a1", "code", False)          # force deep checks
    d = Dispatcher(graph=g, policy=PolicyEngine(), trust=t)
    c = cm(review_cost_minutes=40)
    c.work_kind = "code"
    g.add(c)
    seen = []
    for _ in range(4):
        c.status = Status.PENDING
        d.dispatch(c)
        seen.append(c.review_cost_minutes)
    assert set(seen) == {80}, seen


# --- planning ---------------------------------------------------------------

def test_planner_refuses_unprovable_work():
    """The plan review screen's core claim: work whose completion cannot be
    proven is refused at plan time, by the same gate the live agent uses."""
    from conductor.planning import propose
    p = propose()
    titles = {r["title"] for r in p["rejected"]}
    assert "Improve onboarding" in titles          # no evidence
    assert "Tidy up the codebase" in titles         # trivial check
    reasons = " ".join(r["reason"] for r in p["rejected"])
    assert "no evidence" in reasons
    assert "trivial" in reasons or "proves nothing" in reasons


def test_judgment_calls_are_marked_not_assigned():
    from conductor.planning import propose
    p = propose()
    decisions = [c for c in p["commitments"] if c["judgment"]]
    assert decisions, "expected at least one judgment call in the plan"
    for d in decisions:
        assert d["options"] or d["proof_kind"] == "review"


# --- team -------------------------------------------------------------------

def test_team_interleaves_humans_and_agents_with_delegation():
    """The team screen's claim: an agent is a colleague with a record, and a
    delegate carries its principal, not its own authority."""
    from conductor.server import team
    c = build()
    c.run(ticks=3)
    t = team(c)
    ids = {m["id"]: m for m in t["members"]}
    assert ids["human_sam"]["type"] == "human"
    assert ids["agent_impl"]["type"] == "agent"
    # The delegate acts for a person and starts on probation like any agent.
    d = ids["agent_delegate"]
    assert d["principal"] == "human_sam"
    assert d["probation"] is True


def test_hiring_proposals_are_only_for_non_judgment_work():
    from conductor.server import team
    c = build()
    c.run(ticks=4)
    for p in team(c)["proposals"]:
        assert p["kind"] not in ("product", "design")   # judgment kinds


# --- real execution substrate -----------------------------------------------

def test_only_verified_work_reaches_the_base(tmp_path):
    """The core guarantee, made literal: an agent's work runs in a real git
    worktree and the base advances only when its evidence passes. Wrong work
    is discarded and leaves no trace."""
    import subprocess
    from conductor.execution import GitExecutor, init_repo

    repo = init_repo(str(tmp_path / "ws"))
    gx = GitExecutor(repo)

    gx.open("c/good")
    open(f"{gx.wt_root}/c_good/f.py", "w").write("def add(a,b): return a+b\n")
    gx.commit("c/good", "work")
    ok, _ = gx.verify_in("c/good", "python3 -c 'import f; assert f.add(2,3)==5'")
    assert ok
    merged, _ = gx.merge("c/good")
    assert merged

    gx.open("c/bad")
    open(f"{gx.wt_root}/c_bad/f.py", "w").write("def add(a,b): return a-b\n")
    gx.commit("c/bad", "claim")
    bad, _ = gx.verify_in("c/bad", "python3 -c 'import f; assert f.add(2,3)==5'")
    assert not bad
    gx.discard("c/bad")

    # The base has the correct implementation and the bad branch is gone.
    assert "return a+b" in open(f"{repo}/f.py").read()
    branches = subprocess.run(["git", "-C", repo, "branch"], capture_output=True,
                              text=True).stdout
    assert "c/bad" not in branches and "c/good" not in branches


def test_loop_verifies_in_worktree_and_merges_only_passing_work(tmp_path):
    """The executor wired into the loop: dispatched work runs in a real
    worktree, and the base advances only for a claim that survives its check."""
    import os, random, subprocess
    from conductor.attention import AttentionBudget
    from conductor.cost import CostLedger
    from conductor.decisions import DecisionSurface
    from conductor.dispatcher import Dispatcher
    from conductor.execution import GitExecutor, init_repo
    from conductor.loop import Conductor
    from conductor.policy import PolicyEngine
    from conductor.speculation import SpeculationEngine
    from conductor.verification import VerificationRunner

    repo = init_repo(str(tmp_path / "ws")); gx = GitExecutor(repo)

    class W:
        id = "agent_impl"
        def __init__(s): s.rng = random.Random(2)
        def dispatch(s, cm, context=""):
            cm.attempts += 1; cm.owner = s.id
            cm.status = Status.DISPATCHED; cm.last_signal = now()
            wt = gx.open(cm.branch)
            body = "return a+b" if cm.attempts > 1 else "return a-b"
            open(os.path.join(wt, "feature.py"), "w").write(f"def add(a,b): {body}\n")
            cm.status = Status.CLAIMED_DONE; cm.last_signal = now()

    g = CommitmentGraph()
    g.add_resource(Resource("human_sam", ResourceType.HUMAN, "Sam"))
    g.add_resource(Resource("agent_impl", ResourceType.AGENT, "impl-agent", ["code"]))
    c = cm("Implement add()", spec="python3 -c 'import feature; assert feature.add(2,3)==5'",
           work_kind="code", review_cost_minutes=10)
    c.branch = "conductor/cm_add"; g.add(c)
    t = TrustLedger(); d = Dispatcher(graph=g, policy=PolicyEngine(), trust=t)
    d.budgets["human_sam"] = AttentionBudget("human_sam", 120); d.workers = {"agent_impl": W()}
    C = Conductor(graph=g, verifier=VerificationRunner(workdir=repo), dispatcher=d,
                  surface=DecisionSurface(graph=g), speculation=SpeculationEngine(graph=g),
                  trust=t, cost=CostLedger(), executor=gx)
    C.run(ticks=8)

    assert c.status is Status.DONE
    assert "return a+b" in open(os.path.join(repo, "feature.py")).read()
    assert t.get("agent_impl", "code").failures == 1   # the wrong first attempt
    assert t.get("agent_impl", "code").passes == 1


def test_real_repo_run_merges_only_verified_code(tmp_path):
    """The reproducible real-git demo: wrong code is caught by its check and
    never reaches the base; the base ends holding only correct implementations."""
    import os, subprocess, importlib.util
    from conductor.realworld import build

    c = build(str(tmp_path / "ws"))
    c.run(ticks=10)
    q = [d for d in c.surface.queue() if len(d.options) >= 2]
    if q:
        c.answer(q[0].id, q[0].options[0]); c.run(ticks=6)

    repo = c.executor.repo
    # Every code task is done; the two buggy-first ones took a retry.
    by_title = {cm.title: cm for cm in c.graph}
    assert by_title["Implement slugify(text)"].status is Status.DONE
    assert by_title["Implement slugify(text)"].attempts == 2
    assert by_title["Implement exponential backoff(attempt)"].attempts == 2
    assert c.metrics.claims_rejected >= 2      # the wrong first attempts

    # The correct implementations are what landed on the base.
    for name, call, want in (("slugify", lambda m: m.slugify("Hello World"), "hello-world"),
                             ("backoff", lambda m: m.backoff(3), 8)):
        p = os.path.join(repo, f"{name}.py")
        spec = importlib.util.spec_from_file_location(name, p)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        assert call(mod) == want

    # No conductor worktree branches survive.
    branches = subprocess.run(["git", "-C", repo, "branch"], capture_output=True, text=True).stdout
    assert "conductor/" not in branches


# --- production hardening ---------------------------------------------------

def test_retry_absorbs_transient_faults_but_not_real_errors():
    from conductor.resilience import with_retry, is_retryable
    assert is_retryable(RuntimeError("429 Too Many Requests"))
    assert is_retryable(Exception("event loop cycle failed"))
    assert not is_retryable(ValueError("bad input"))

    calls = [0]
    def flaky():
        calls[0] += 1
        if calls[0] < 3:
            raise RuntimeError("503 unavailable")
        return "ok"
    assert with_retry(flaky, max_retries=5, base=1.001, cap=0.01) == "ok"
    assert calls[0] == 3

    import pytest
    with pytest.raises(ValueError):
        with_retry(lambda: (_ for _ in ()).throw(ValueError("nope")),
                   max_retries=3, base=1.001)


def test_server_health_and_input_validation():
    import json, threading, time, urllib.request, urllib.error
    from conductor.server import serve
    c = build(); c.run(ticks=2)
    port = 7691
    threading.Thread(target=serve, args=(c,),
                     kwargs={"port": port, "open_browser": False}, daemon=True).start()
    time.sleep(0.5)
    base = f"http://127.0.0.1:{port}"

    h = json.load(urllib.request.urlopen(base + "/api/health"))
    assert h["status"] == "ok" and "commitments" in h

    def post(path, data):
        req = urllib.request.Request(base + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code

    assert post("/api/tick", b"not json") == 400
    assert post("/api/answer", b"{}") == 400
    assert post("/api/answer", b'{"decision_id":"nope","choice":"x"}') in (404, 500)


def test_config_selects_store_from_environment(tmp_path, monkeypatch):
    from conductor.events import JsonlStore, MemoryStore
    import importlib, conductor.config as cfg

    monkeypatch.delenv("CONDUCTOR_TABLE", raising=False)
    monkeypatch.delenv("CONDUCTOR_EVENT_LOG", raising=False)
    importlib.reload(cfg)
    assert isinstance(cfg.Config().store(), MemoryStore)

    monkeypatch.setenv("CONDUCTOR_EVENT_LOG", str(tmp_path / "e.jsonl"))
    importlib.reload(cfg)
    assert isinstance(cfg.Config().store(), JsonlStore)
    monkeypatch.delenv("CONDUCTOR_EVENT_LOG", raising=False)
    importlib.reload(cfg)


def test_server_state_survives_restart(tmp_path):
    """Durability: a fresh process resuming the same log rebuilds the work and
    the trust the previous one left, and continues onto the same log."""
    from conductor.events import JsonlStore
    from conductor.world import persistent

    log = str(tmp_path / "c.jsonl")

    c1 = persistent(store=JsonlStore(log), tenant="acme")
    c1.run(ticks=6)
    done1 = {x.id: x.status for x in c1.graph if x.status is Status.DONE}
    trust1 = {k: (r.passes, r.failures) for k, r in c1.trust.records.items()}
    assert done1 and trust1

    c2 = persistent(store=JsonlStore(log), tenant="acme")   # restart
    done2 = {x.id: x.status for x in c2.graph if x.status is Status.DONE}
    trust2 = {k: (r.passes, r.failures) for k, r in c2.trust.records.items()}
    assert done2 == done1
    assert trust2 == trust1

    before = sum(1 for _ in open(log))
    c2.run(ticks=6)
    assert sum(1 for _ in open(log)) > before      # continues onto the same log

    # A different tenant on the same store is isolated.
    c3 = persistent(store=JsonlStore(log), tenant="other")
    assert not any(x.id in done1 for x in c3.graph)


# --- ASGI service: concurrency, auth, observability -------------------------

def _client():
    from fastapi.testclient import TestClient
    import importlib, conductor.asgi as asgi
    importlib.reload(asgi)
    return TestClient(asgi.app), asgi


def test_asgi_health_and_demo_mode(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    c, _ = _client()
    h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["auth"] == "disabled"
    assert c.get("/api/state").status_code == 200          # no auth needed
    r = c.post("/api/tick", json={"ticks": 2})
    assert r.status_code == 200 and "x-request-id" in r.headers


def test_asgi_real_execution_merges_only_verified(monkeypatch):
    """The real-execution endpoint runs the loop against a real git repo and
    merges only work whose real check passed. The confident-but-wrong slugify is
    caught, so the version on the base branch is the correct, lowercased one."""
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    c, _ = _client()
    r = c.post("/api/real/run", json={"ticks": 10, "live": False})
    assert r.status_code == 200
    d = r.json()
    assert d["metrics"]["claims_rejected"] >= 1               # a lie was caught
    assert d["metrics"]["verified"] >= 1
    slug = d["repo"]["files"].get("slugify.py", "")
    assert "lower()" in slug                                   # only the fixed one merged
    assert any("merge" in ln for ln in d["repo"]["log"])       # real merge commits
    # An unknown decision is a 404, not a 200 with an error body.
    assert c.get("/api/decision?id=nope").status_code == 404


def test_asgi_repo_flow_gated_and_validated(monkeypatch, tmp_path):
    """Connecting a real repo is off unless CONDUCTOR_ALLOW_REPO=1 (it runs real
    commands against the repo). When on, only an actual git repo connects, and a
    task can be added; a live agent then does the work behind the same gate."""
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    monkeypatch.delenv("CONDUCTOR_ALLOW_REPO", raising=False)
    c, _ = _client()
    assert c.get("/api/repo").json()["enabled"] is False
    assert c.post("/api/repo/connect", json={"path": str(tmp_path)}).status_code == 403

    monkeypatch.setenv("CONDUCTOR_ALLOW_REPO", "1")
    c, _ = _client()
    assert c.get("/api/repo").json() == {"enabled": True, "connected": False, "path": None}
    # A non-repo directory is rejected.
    assert c.post("/api/repo/connect", json={"path": str(tmp_path)}).status_code == 400
    # A real git repo connects.
    import subprocess
    for args in (["init", "-q"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    (tmp_path / "README.md").write_text("# x\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "base"], check=True)
    r = c.post("/api/repo/connect", json={"path": str(tmp_path)})
    assert r.status_code == 200 and r.json()["connected"] is True
    # A task needs all three fields.
    assert c.post("/api/repo/task", json={"title": "x", "file": "x.py"}).status_code == 400
    r = c.post("/api/repo/task", json={"title": "Implement f", "file": "f.py",
                                       "check": "python3 -c 'import f'"})
    assert r.status_code == 200 and len(r.json()["board"]) == 1


def test_asgi_demo_visitors_are_isolated_and_rate_limited(monkeypatch):
    """In demo mode each visitor gets their own cookie-scoped board (one cannot
    reset or drive another's), the planner is rate limited, and an oversized
    intent is capped rather than passed through to the model."""
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "0")
    c, asgi = _client()
    asgi._rate.clear()
    from fastapi.testclient import TestClient

    a, b = TestClient(asgi.app), TestClient(asgi.app)
    a.post("/api/tick", json={"ticks": 6})                    # A drives its board
    assert a.get("/api/state").json()["metrics"]["verified"] >= 1
    assert b.get("/api/state").json()["metrics"]["verified"] == 0   # B is untouched
    assert a.cookies.get("conductor_demo") != b.cookies.get("conductor_demo")

    # Rate limit: the 13th plan in the window is rejected.
    codes = [a.post("/api/plan", json={"intent": "x"}).status_code for _ in range(14)]
    assert codes.count(200) == 12 and 429 in codes

    # Oversized intent is capped, not forwarded whole.
    asgi._rate.clear()
    r = b.post("/api/plan", json={"intent": "a" * 10000})
    assert r.status_code == 200


def test_asgi_enforced_auth_and_tenant_isolation(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "1")
    monkeypatch.setenv("CONDUCTOR_SESSION_SECRET", "test-secret")
    c, asgi = _client()
    from conductor.auth import mint_session

    assert c.get("/api/state").status_code == 401          # no session

    tok_a, tok_b = mint_session("a", "acme"), mint_session("b", "beta")
    c.post("/api/tick", json={"ticks": 5}, headers={"Authorization": f"Bearer {tok_a}"})
    sa = c.get("/api/state", headers={"Authorization": f"Bearer {tok_a}"}).json()
    sb = c.get("/api/state", headers={"Authorization": f"Bearer {tok_b}"}).json()
    done_a = sum(1 for x in sa["board"] if x["status"] == "done")
    done_b = sum(1 for x in sb["board"] if x["status"] == "done")
    assert done_a > 0 and done_b == 0                       # isolated conductors


def test_asgi_rejects_tampered_session(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_REQUIRE_AUTH", "1")
    monkeypatch.setenv("CONDUCTOR_SESSION_SECRET", "test-secret")
    c, _ = _client()
    from conductor.auth import mint_session
    tok = mint_session("a", "acme")
    bad = tok[:-4] + "aaaa"
    assert c.get("/api/state", headers={"Authorization": f"Bearer {bad}"}).status_code == 401
