"""Connect Conductor to a real repository you own.

This is the authenticated / local mode of real execution. Unlike the sandbox in
realworld.py, the backlog is yours: you describe a task and the exact check that
proves it, and a live Strands agent writes code into a real worktree off your
base branch. The check runs as a real command; a pass merges into your LOCAL
base, a failure is discarded. Conductor never pushes to a remote.

Because a task's check is an arbitrary command run against your repo, this is
real code execution by design. It is therefore gated behind CONDUCTOR_ALLOW_REPO
and is never enabled on the public demo. Turn it on deliberately, locally.
"""

from __future__ import annotations

import os

from .attention import AttentionBudget
from .cost import CostLedger
from .decisions import DecisionSurface
from .dispatcher import Dispatcher
from .execution import GitExecutor
from .graph import CommitmentGraph
from .loop import Conductor
from .models import (Commitment, Evidence, EvidenceKind, Resource, ResourceType)
from .policy import PolicyEngine
from .roster import AgentSpec
from .speculation import SpeculationEngine
from .trust import TrustLedger
from .verification import VerificationRunner
from .workers import StrandsWorker


def repo_enabled() -> bool:
    """Real-repo execution is off unless the operator deliberately turns it on."""
    return os.environ.get("CONDUCTOR_ALLOW_REPO", "0") == "1"


def validate_repo(path: str) -> tuple[bool, str]:
    """A connectable repo is an existing directory that is a git work tree."""
    if not path or not path.strip():
        return False, "give a path to a local git repository"
    p = os.path.abspath(os.path.expanduser(path.strip()))
    if not os.path.isdir(p):
        return False, f"no such directory: {p}"
    if not os.path.isdir(os.path.join(p, ".git")):
        return False, f"not a git repository (no .git): {p}"
    return True, p


def build_for_repo(repo_path: str, worker_factory=None) -> Conductor:
    """A Conductor pointed at a real repo with an empty backlog. The agent is a
    live Strands worker; work is added later with add_task()."""
    repo = os.path.abspath(os.path.expanduser(repo_path))
    gx = GitExecutor(repo)

    g = CommitmentGraph()
    g.add_resource(Resource("you", ResourceType.HUMAN, "You", ["product"]))
    agent = Resource("agent_impl", ResourceType.AGENT, "impl-agent", ["code"])
    agent.spec = AgentSpec(
        purpose="Write small, correct code. You are given the exact check that "
                "will run against your file; satisfy it precisely and honestly.",
        work_kinds=["code"])
    g.add_resource(agent)

    trust, cost = TrustLedger(), CostLedger()
    disp = Dispatcher(graph=g, policy=PolicyEngine(autonomy=0.6), trust=trust)
    disp.budgets["you"] = AttentionBudget("you", minutes_per_day=120)
    make = worker_factory or (lambda: StrandsWorker(agent, executor=gx, ledger=cost))
    disp.workers = {"agent_impl": make()}

    return Conductor(
        graph=g, verifier=VerificationRunner(workdir=repo), dispatcher=disp,
        surface=DecisionSurface(graph=g), speculation=SpeculationEngine(graph=g),
        trust=trust, cost=cost, executor=gx)


def add_task(c: Conductor, title: str, file: str, check: str,
             work_kind: str = "code", review_cost: int = 10) -> Commitment:
    """Add one task: a title, the file the agent should produce, and the exact
    command that proves it. The command is the contract for 'done'."""
    cm = Commitment.new(
        title.strip() or "Untitled task",
        Evidence(EvidenceKind.COMMAND, spec=check.strip(),
                 description=f"{check.strip()} must exit 0"),
        work_kind=work_kind, review_cost_minutes=review_cost)
    cm.artifact_path = file.strip()
    cm.branch = f"conductor/{cm.id}"
    c.graph.add(cm)
    return cm
