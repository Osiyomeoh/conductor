"""Dispatcher: the only path from plan to the world.

Two rules it never breaks:
  1. Work is dispatched only if the reviewer's remaining attention can absorb
     the review it will create. Otherwise it is HELD, with the reason.
  2. Agent work runs isolated. Nothing merges until its evidence passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .attention import AttentionBudget
from .models import Action, Commitment, Decision as PolicyDecision, ResourceType, Status
from .policy import PolicyEngine
from .trust import TrustLedger


@dataclass
class Dispatcher:
    graph: object
    policy: PolicyEngine
    trust: TrustLedger
    budgets: dict[str, AttentionBudget] = field(default_factory=dict)
    workers: dict[str, object] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def budget_for(self, reviewer: str) -> AttentionBudget:
        return self.budgets.setdefault(reviewer, AttentionBudget(reviewer))

    def dispatch(self, cm: Commitment) -> bool:
        worker = self.graph.pick_worker(cm, self.trust)
        if worker is None:
            cm.log("no eligible worker")
            return False

        reviewer = cm.reviewer or self._default_reviewer()
        cm.reviewer = reviewer
        budget = self.budget_for(reviewer)

        # Deeper distrust means a costlier review. Trust is priced, not assumed.
        depth = self.trust.evidence_depth(worker.id, cm.work_kind)
        if cm.base_review_cost is None:
            cm.base_review_cost = cm.review_cost_minutes
        base = cm.base_review_cost
        cm.review_cost_minutes = {"light": max(2, base // 3),
                                  "standard": base,
                                  "deep": base * 2}[depth]

        if not budget.can_absorb(cm):
            budget.hold(cm)
            self.log.append(f"HELD  {cm.title}  ({budget.summary()})")
            return False

        action = Action(kind="dispatch", commitment_id=cm.id,
                        summary=f"dispatch {cm.title} to {worker.id}",
                        irreversible=False,
                        external=worker.type is ResourceType.HUMAN,
                        payload={"touches_production": cm.consequential and not cm.branch})
        verdict = self.policy.evaluate(action, worker)
        if verdict.decision is PolicyDecision.BLOCK:
            cm.status = Status.ESCALATED
            cm.log(f"policy BLOCK: {'; '.join(verdict.reasons)}")
            self.log.append(f"BLOCK {cm.title}  {verdict.reasons}")
            return False
        if verdict.decision is PolicyDecision.APPROVE:
            cm.status = Status.ESCALATED
            cm.log(f"policy APPROVE required: {'; '.join(verdict.reasons)}")
            return False

        if worker.type is ResourceType.AGENT and cm.branch is None:
            cm.branch = f"conductor/{cm.id}"
            cm.log(f"isolated on {cm.branch}")

        budget.reserve(cm)
        impl = self.workers.get(worker.id)
        if impl is None:
            cm.status = Status.DISPATCHED
            cm.log(f"assigned to {worker.id}; awaiting external signal")
        else:
            impl.dispatch(cm)
        self.log.append(f"DISP  {cm.title} -> {worker.id} (evidence: {depth})")
        return True

    def _default_reviewer(self) -> str:
        for r in self.graph.resources.values():
            if r.type is ResourceType.HUMAN:
                return r.id
        return "human_owner"
