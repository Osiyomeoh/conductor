"""A real-repo run of the whole loop, driven by a deterministic worker.

No model, no network, no throttle. The worker writes real Python into real git
worktrees; the evidence runs as real commands; passing work is merged with real
merge commits and failing work is discarded. Everything the live agent path
does, minus the language model, so the core guarantee can be shown end to end
and reproduced byte for byte.

The point it makes on screen: an agent writes confident, plausible, wrong code;
the check catches it before any human looks; recovery re-dispatches; the second
attempt passes and merges. The base repository ends holding only verified work.
"""

from __future__ import annotations

import os
from random import Random

from .attention import AttentionBudget
from .cost import CostLedger
from .decisions import DecisionSurface
from .dispatcher import Dispatcher
from .execution import GitExecutor, init_repo
from .graph import CommitmentGraph
from .loop import Conductor
from .models import (Commitment, Evidence, EvidenceKind, Resource, ResourceType,
                     Status, now)
from .policy import PolicyEngine
from .speculation import SpeculationEngine
from .trust import TrustLedger
from .verification import VerificationRunner


# A small real backlog: each task is one file, with a correct implementation
# and, for the ones that fail first, a plausible-but-wrong one.
TASKS = {
    "add": {
        "file": "add.py", "kind": "code", "cost": 8,
        "title": "Implement add(a, b)",
        "check": "python3 -c 'import add; assert add.add(2,3)==5 and add.add(-1,1)==0'",
        "good": "def add(a, b):\n    return a + b\n",
        "bad": None,
    },
    "is_even": {
        "file": "is_even.py", "kind": "code", "cost": 8,
        "title": "Implement is_even(n)",
        "check": "python3 -c 'import is_even; assert is_even.is_even(4) and not is_even.is_even(3)'",
        "good": "def is_even(n):\n    return n % 2 == 0\n",
        "bad": None,
    },
    "slugify": {
        "file": "slugify.py", "kind": "code", "cost": 12,
        "title": "Implement slugify(text)",
        "check": "python3 -c \"import slugify; assert slugify.slugify('Hello World')=='hello-world'\"",
        # Confident and plausible: spaces to hyphens, but forgets to lowercase.
        "bad": "def slugify(text):\n    return text.replace(' ', '-')\n",
        "good": "def slugify(text):\n    return text.lower().replace(' ', '-')\n",
    },
    "retry_backoff": {
        "file": "backoff.py", "kind": "code", "cost": 15,
        "title": "Implement exponential backoff(attempt)",
        "check": "python3 -c 'import backoff; assert backoff.backoff(0)==1 and backoff.backoff(3)==8'",
        # Off by one in the exponent: looks right, is wrong.
        "bad": "def backoff(attempt):\n    return 2 ** (attempt + 1)\n",
        "good": "def backoff(attempt):\n    return 2 ** attempt\n",
    },
}


class CodeWorker:
    """Writes real code into the commitment's worktree. Deterministic: the
    tasks named in `buggy_first` get the wrong implementation on attempt one and
    the correct one on the retry, so the caught-bug story is reproducible."""

    def __init__(self, resource_id: str, executor: GitExecutor,
                 buggy_first: set[str] | None = None):
        self.id = resource_id
        self.executor = executor
        self.buggy_first = buggy_first or set()

    def dispatch(self, cm: Commitment, context: str = "") -> None:
        cm.attempts += 1
        cm.owner = self.id
        cm.status = Status.DISPATCHED
        cm.last_signal = now()
        wt = self.executor.open(cm.branch)
        task = TASKS[cm.task_key]
        use_bad = task["bad"] and cm.task_key in self.buggy_first and cm.attempts == 1
        code = task["bad"] if use_bad else task["good"]
        with open(os.path.join(wt, task["file"]), "w") as f:
            f.write(code)
        cm.status = Status.CLAIMED_DONE
        cm.last_signal = now()
        cm.log(f"{self.id} wrote {task['file']} in {cm.branch}"
               + (" (confident, wrong)" if use_bad else ""))


def build(repo_path: str, live: bool = False) -> Conductor:
    repo = init_repo(repo_path)
    gx = GitExecutor(repo)

    g = CommitmentGraph()
    g.add_resource(Resource("human_sam", ResourceType.HUMAN, "Sam", ["product"]))
    g.add_resource(Resource("agent_impl", ResourceType.AGENT, "impl-agent", ["code"]))

    for key, t in TASKS.items():
        cm = Commitment.new(
            t["title"], Evidence(EvidenceKind.COMMAND, spec=t["check"]),
            work_kind=t["kind"], review_cost_minutes=t["cost"])
        cm.task_key = key
        cm.artifact_path = t["file"]
        cm.branch = f"conductor/{cm.id}"
        g.add(cm)

    # One genuine judgment call, to show the loop still stops for a human.
    api = Commitment.new(
        "Decide the public API surface",
        Evidence(EvidenceKind.HUMAN_REVIEW, description="product judgment"),
        ambiguous=True, work_kind="product", review_cost_minutes=20,
        options=["flat module functions", "a single Client class",
                 "both, class wrapping functions"])
    g.add(api)

    trust, cost = TrustLedger(), CostLedger()
    disp = Dispatcher(graph=g, policy=PolicyEngine(autonomy=0.6), trust=trust)
    disp.budgets["human_sam"] = AttentionBudget("human_sam", minutes_per_day=90)
    if live:
        # A real Strands agent (provider from CONDUCTOR_PROVIDER) writing real
        # code into real worktrees. Whether it is correct is decided by the
        # evidence, exactly as with the deterministic worker.
        from .roster import AgentSpec
        from .workers import StrandsWorker
        g.resources["agent_impl"].spec = AgentSpec(
            purpose="Write small, correct Python. You are given the exact check "
                    "that will run against your file; satisfy it precisely.",
            work_kinds=["code"])
        disp.workers = {"agent_impl": StrandsWorker(
            g.resources["agent_impl"], executor=gx, ledger=cost)}
    else:
        # slugify and backoff come back wrong first; the check catches both.
        disp.workers = {"agent_impl": CodeWorker("agent_impl", gx,
                                                 buggy_first={"slugify", "retry_backoff"})}

    return Conductor(
        graph=g, verifier=VerificationRunner(workdir=repo), dispatcher=disp,
        surface=DecisionSurface(graph=g), speculation=SpeculationEngine(graph=g),
        trust=trust, cost=cost, executor=gx)
