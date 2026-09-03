"""Speculative execution across open decisions.

Every project tool ever built stops when it hits a decision only a human can
make, and calls the dead time "waiting on stakeholder". That dead time is the
largest single source of delay in any project and no tool measures it.

Agent labour is now cheap and parallel. So instead of waiting, Conductor forks
the plan across the plausible answers, builds and verifies every branch in
isolation, and discards the losers when the human answers. You pay 3x nearly
nothing to buy back a night of project time.

This only became rational about eighteen months ago, which is precisely why
none of the incumbents do it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .decisions import Decision
from .models import Commitment, Status


@dataclass
class Branch:
    id: str
    decision_id: str
    option: str
    commitments: list[str] = field(default_factory=list)
    cost: float = 0.0
    verified: int = 0
    rejected: int = 0
    discarded: bool = False


@dataclass
class SpeculationEngine:
    graph: object
    max_branches_per_decision: int = 3
    max_cost_per_decision: float = 2.0     # dollars; must stay visibly cheap
    branches: dict[str, Branch] = field(default_factory=dict)

    def fork(self, decision: Decision, plan_fn) -> list[Branch]:
        """`plan_fn(option, blocked_commitment) -> list[Commitment]` is supplied
        by the Planner agent: what work becomes possible if this answer holds."""
        made: list[Branch] = []
        for option in decision.options[: self.max_branches_per_decision]:
            b = Branch(id=f"spec_{decision.id}_{len(made)}", decision_id=decision.id,
                       option=option)
            for cid in decision.blocked:
                for cm in plan_fn(option, self.graph.get(cid)):
                    cm.speculative_for = decision.id
                    cm.assumes = {decision.id: option}
                    cm.branch = b.id
                    cm.status = Status.PENDING
                    cm.log(f"speculative: assumes {decision.id} = {option!r}")
                    self.graph.add(cm)
                    b.commitments.append(cm.id)
            self.branches[b.id] = b
            made.append(b)
        return made

    def budget_exhausted(self, decision_id: str) -> bool:
        spent = sum(b.cost for b in self.branches.values() if b.decision_id == decision_id)
        return spent >= self.max_cost_per_decision

    def resolve(self, decision: Decision) -> tuple[Branch | None, list[Branch]]:
        """Human answered. Keep the branch that assumed correctly, discard the rest."""
        keep, drop = None, []
        for b in self.branches.values():
            if b.decision_id != decision.id or b.discarded:
                continue
            if b.option == decision.answer:
                keep = b
            else:
                b.discarded = True
                drop.append(b)
                for cid in b.commitments:
                    cm = self.graph.get(cid)
                    cm.status = Status.BLOCKED
                    cm.log(f"discarded: {decision.id} resolved to {decision.answer!r}")
        return keep, drop

    def report(self, decision_id: str) -> str:
        bs = [b for b in self.branches.values() if b.decision_id == decision_id]
        if not bs:
            return "no speculation"
        cost = sum(b.cost for b in bs)
        done = sum(b.verified for b in bs if not b.discarded)
        return (f"{len(bs)} branches speculated, ${cost:.2f} spent, "
                f"{done} commitments already verified against the chosen answer")
