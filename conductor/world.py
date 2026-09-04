"""A seeded sprint, mixed human and agent, with the failure modes that matter."""

from __future__ import annotations

import os
import shutil

from .attention import AttentionBudget
from .decisions import DecisionSurface
from .dispatcher import Dispatcher
from .events import Recorder
from .graph import CommitmentGraph
from .loop import Conductor
from .models import Commitment, Evidence, EvidenceKind, Resource, ResourceType
from .policy import PolicyEngine
from .speculation import SpeculationEngine
from .trust import TrustLedger
from .cost import CostLedger
from .verification import VerificationRunner
from .workers import SilentWorker, SimulatedWorker

# The dispatch workspace. Defaults to a .work dir beside the package, but honours
# CONDUCTOR_WORK_DIR so a read-only deployment (e.g. AgentCore Runtime, where /app
# is root-owned and the process is non-root) can point it at a writable path.
WORKDIR = os.environ.get("CONDUCTOR_WORK_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".work")


def _cm(title, token, kind, **kw) -> Commitment:
    art = kw.pop("artifact", None) or f"{kind}.txt"
    cm = Commitment.new(
        title=title,
        evidence=Evidence(EvidenceKind.COMMAND, spec=f"grep -q {token} {art}",
                          description=f"artifact must contain {token}"),
        work_kind=kind, **kw)
    cm.artifact_path, cm.expected_token = art, token
    return cm


def build(seed: int = 7, store=None, tenant: str = "default",
          repo: str | None = None, seed_commitments: bool = True) -> Conductor:
    shutil.rmtree(WORKDIR, ignore_errors=True)
    os.makedirs(WORKDIR, exist_ok=True)

    recorder = Recorder(store, tenant)
    g = CommitmentGraph(recorder=recorder)
    g.add_resource(Resource("human_sam", ResourceType.HUMAN, "Sam", ["product", "judgment"],
                            scopes=["repo:read", "repo:write:branch", "docs:write"]))
    g.add_resource(Resource("human_sarah", ResourceType.HUMAN, "Sarah", ["design"],
                            scopes=["repo:read", "design:write"]))
    g.add_resource(Resource("agent_impl", ResourceType.AGENT, "impl-agent", ["code"],
                            scopes=["repo:read", "repo:write:branch"]))
    g.add_resource(Resource("agent_research", ResourceType.AGENT, "research-agent", ["research"],
                            scopes=["repo:read"]))
    # An agent that acts for a person: inherits Sam's scopes, reviewed by Sam.
    g.add_resource(Resource("agent_delegate", ResourceType.AGENT, "sam's delegate",
                            ["review-prep"], principal="human_sam",
                            scopes=["repo:read", "repo:write:branch", "docs:write"]))

    webhook = _cm("Fix the payment webhook retry", "RETRY_OK", "code",
                  artifact="webhook.txt", review_cost_minutes=20)
    tests = _cm("Add webhook regression tests", "TESTS_OK", "code",
                artifact="tests.txt", review_cost_minutes=15)
    tests.dependencies = [webhook.id]
    research = _cm("Competitive research on three tools", "RESEARCH_OK", "research",
                   artifact="research.txt", review_cost_minutes=10)
    migration = _cm("Migrate the onboarding events table", "MIGRATION_OK", "code",
                    artifact="migration.txt", review_cost_minutes=25)
    copy = _cm("Rewrite onboarding empty states", "COPY_OK", "content",
               artifact="copy.txt", review_cost_minutes=10)
    pricing = Commitment.new(
        "Decide the onboarding paywall position",
        Evidence(EvidenceKind.HUMAN_REVIEW, description="product judgment"),
        ambiguous=True, work_kind="product", review_cost_minutes=30,
        options=["paywall after first value moment", "paywall on signup",
                 "no paywall, usage limit instead"])
    design = Commitment.new(
        "Redesign the onboarding flow",
        Evidence(EvidenceKind.HUMAN_REVIEW, description="design review"),
        ambiguous=True, work_kind="design", owner="human_sarah", review_cost_minutes=30)
    design.dependencies = [pricing.id]

    if seed_commitments:
        for c in (webhook, tests, research, migration, copy, pricing, design):
            g.add(c)

    trust = TrustLedger()
    cost = CostLedger()
    policy = PolicyEngine(autonomy=0.6)
    verifier = VerificationRunner(workdir=WORKDIR)
    disp = Dispatcher(graph=g, policy=policy, trust=trust)
    disp.budgets["human_sam"] = AttentionBudget("human_sam", minutes_per_day=150)
    disp.workers = {
        # Competent on research, unreliable on code: the confident-and-wrong case.
        "agent_impl": SimulatedWorker("agent_impl", WORKDIR, competence=0.45, seed=seed, ledger=cost),
        "agent_research": SimulatedWorker("agent_research", WORKDIR, competence=0.9, seed=seed, ledger=cost),
        "human_sarah": SilentWorker("human_sarah", WORKDIR, seed=seed),
    }

    surface = DecisionSurface(graph=g)
    spec = SpeculationEngine(graph=g, ledger=cost)

    # Real mode: agent work runs in git worktrees against `repo`, merged only
    # on a passing check. Left None, the seeded demo uses the scratch dir.
    executor = None
    if repo:
        from .execution import GitExecutor, init_repo
        executor = GitExecutor(init_repo(repo))
    return Conductor(graph=g, verifier=verifier, dispatcher=disp, surface=surface,
                     speculation=spec, trust=trust, cost=cost,
                     recorder=recorder, executor=executor)


def hire_agent(c, kind: str, competence: float = 0.8) -> str:
    """Hire an agent for a kind of work: add it to the roster on probation and
    give it a worker so it can actually be dispatched. Returns the new agent id."""
    import uuid
    from .roster import AgentSpec, Roster
    from .workers import SimulatedWorker
    aid = f"agent_{kind}_{uuid.uuid4().hex[:6]}"
    spec = AgentSpec(
        purpose=f"Handle {kind} work end to end, producing output whose "
                f"correctness can be checked mechanically.",
        work_kinds=[kind], scopes=["repo:read", "repo:write:branch"])
    Roster(graph=c.graph, trust=c.trust).hire(aid, f"{kind}-agent", spec)
    c.dispatcher.workers[aid] = SimulatedWorker(
        aid, WORKDIR, competence=competence,
        seed=abs(hash(aid)) % 1000, ledger=c.cost)
    from .events import EventKind
    if getattr(c, "recorder", None) is not None:
        c.recorder.record(EventKind.HIRED, actor=aid, work_kind=kind)
    c.emit(f"hired {aid} for {kind} work, on probation")
    return aid


def persistent(store=None, tenant: str = "default", seed: int = 7,
               repo: str | None = None):
    """Resume from a durable log if one exists for this tenant, otherwise seed
    a fresh sprint. Either way the returned Conductor has a fully wired
    dispatcher, workers, budgets and trust; only the commitments and their
    outcomes come from the log on resume.

    This is what makes the running server durable: a restart rebuilds the work
    and the trust the previous process left, and continues recording onto the
    same log."""
    from .config import CONFIG
    from .replay import rebuild
    store = store or CONFIG.store()
    resuming = store.last_seq(tenant) > 0

    # Build the scaffold. On resume, suppress recording and add no seed
    # commitments, so replaying the log is the only source of state.
    c = build(seed=seed, store=store, tenant=tenant, repo=repo,
              seed_commitments=not resuming)
    if resuming:
        c.recorder.replaying = True
        try:
            seq = rebuild(c.graph, c.recorder.history(), trust=c.trust)
        finally:
            c.recorder.replaying = False
        c.emit(f"resumed from durable log at sequence {seq}")
    return c
