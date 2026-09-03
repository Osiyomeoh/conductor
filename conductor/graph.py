"""The commitment graph.

Not a task list. A live graph of who owes what to whom by when, with
dependencies and risk, re-scored every tick. Plans decay in hours once agents
are moving, so nothing here is treated as a document.
"""

from __future__ import annotations

from datetime import timedelta

from .models import Commitment, Resource, Status, now


class CommitmentGraph:
    def __init__(self) -> None:
        self.commitments: dict[str, Commitment] = {}
        self.resources: dict[str, Resource] = {}

    # construction -------------------------------------------------------
    def add(self, cm: Commitment) -> Commitment:
        self.commitments[cm.id] = cm
        return cm

    def add_resource(self, r: Resource) -> Resource:
        self.resources[r.id] = r
        return r

    # queries ------------------------------------------------------------
    def __iter__(self):
        return iter(self.commitments.values())

    def get(self, cid: str) -> Commitment:
        return self.commitments[cid]

    def deps_satisfied(self, cm: Commitment) -> bool:
        return all(self.commitments[d].status is Status.DONE
                   for d in cm.dependencies if d in self.commitments)

    def ready(self) -> list[Commitment]:
        return [c for c in self
                if c.status in (Status.PENDING, Status.HELD, Status.REJECTED)
                and self.deps_satisfied(c)]

    def claimed(self) -> list[Commitment]:
        return [c for c in self if c.status is Status.CLAIMED_DONE]

    def in_flight(self) -> list[Commitment]:
        return [c for c in self if c.status is Status.DISPATCHED]

    def blocking_count(self, cid: str) -> int:
        """How many commitments transitively wait on this one."""
        seen, stack = set(), [cid]
        while stack:
            cur = stack.pop()
            for c in self:
                if cur in c.dependencies and c.id not in seen:
                    seen.add(c.id)
                    stack.append(c.id)
        return len(seen)

    # risk ---------------------------------------------------------------
    def score_risk(self, cm: Commitment) -> float:
        risk = 0.0
        if cm.deadline:
            left = (cm.deadline - now()).total_seconds() / 3600
            if left < 0:
                risk += 0.5
            elif left < 24:
                risk += 0.3
            elif left < 72:
                risk += 0.15
        silent_h = cm.silent_for / timedelta(hours=1)
        if cm.status is Status.DISPATCHED:
            risk += min(0.3, silent_h / 24 * 0.3)
        risk += min(0.25, 0.08 * cm.attempts)
        risk += min(0.2, 0.04 * self.blocking_count(cm.id))
        owner = self.resources.get(cm.owner or "")
        if owner and owner.reliability < 0.7:
            risk += 0.1
        return round(min(risk, 1.0), 3)

    def drifting(self, threshold: float = 0.45) -> list[Commitment]:
        out = []
        for c in self:
            if c.terminal or c.status is Status.ESCALATED:
                continue
            if self.score_risk(c) >= threshold:
                out.append(c)
        return sorted(out, key=self.score_risk, reverse=True)

    # routing ------------------------------------------------------------
    def pick_worker(self, cm: Commitment, trust=None):
        """Judgment, ambiguity and consequence go to humans. Checkable volume
        goes to agents. Within a pool, pick on trust for this kind of work."""
        want_human = cm.ambiguous or cm.consequential
        pool = [r for r in self.resources.values()
                if (r.type.value == "human") == want_human]
        if not pool:
            pool = list(self.resources.values())
        if cm.owner and cm.owner in self.resources:
            return self.resources[cm.owner]

        def rank(r):
            skill = 1.0 if cm.work_kind in r.skills else 0.0
            score = trust.peek(r.id, cm.work_kind) if trust is not None else r.reliability
            return (skill, score)

        return max(pool, key=rank, default=None)
