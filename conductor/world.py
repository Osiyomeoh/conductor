"""A seeded sprint, mixed human and agent, with the failure modes that matter."""

from __future__ import annotations

import os
import shutil

from .attention import AttentionBudget
from .decisions import DecisionSurface
from .dispatcher import Dispatcher
from .graph import CommitmentGraph
from .loop import Conductor
from .models import Commitment, Evidence, EvidenceKind, Resource, ResourceType
from .policy import PolicyEngine
from .speculation import SpeculationEngine
from .trust import TrustLedger
from .cost import CostLedger
from .verification import VerificationRunner
from .workers import SilentWorker, SimulatedWorker

WORKDIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".work")


def _cm(title, token, kind, **kw) -> Commitment:
    art = kw.pop("artifact", None) or f"{kind}.txt"
    cm = Commitment.new(
        title=title,
        evidence=Evidence(EvidenceKind.COMMAND, spec=f"grep -q {token} {art}",
                          description=f"artifact must contain {token}"),
        work_kind=kind, **kw)
    cm.artifact_path, cm.expected_token = art, token
    return cm


def build(seed: int = 7) -> Conductor:
    shutil.rmtree(WORKDIR, ignore_errors=True)
    os.makedirs(WORKDIR, exist_ok=True)

    g = CommitmentGraph()
    g.add_resource(Resource("human_sam", ResourceType.HUMAN, "Sam", ["product", "judgment"]))
    g.add_resource(Resource("human_sarah", ResourceType.HUMAN, "Sarah", ["design"]))
    g.add_resource(Resource("agent_impl", ResourceType.AGENT, "impl-agent", ["code"]))
    g.add_resource(Resource("agent_research", ResourceType.AGENT, "research-agent", ["research"]))

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
    return Conductor(graph=g, verifier=verifier, dispatcher=disp, surface=surface,
                     speculation=spec, trust=trust, cost=cost)
