"""Attention budgeting.

Agent labour is cheap and parallel. The person who has to review it is not.
Dispatching twelve agent tasks the reviewer cannot check by Friday is not
progress, it is debt with a friendly status colour. So dispatch spends against
a reviewer budget, and when the budget is gone, ready work is HELD.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Commitment, Status


@dataclass
class AttentionBudget:
    reviewer_id: str
    minutes_per_day: int = 120
    spent: int = 0
    committed: int = 0        # reserved by work already in flight
    held: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.minutes_per_day - self.spent - self.committed)

    def can_absorb(self, cm: Commitment) -> bool:
        return cm.review_cost_minutes <= self.remaining

    def reserve(self, cm: Commitment) -> None:
        self.committed += cm.review_cost_minutes

    def release(self, cm: Commitment, consumed: bool) -> None:
        self.committed = max(0, self.committed - cm.review_cost_minutes)
        if consumed:
            self.spent += cm.review_cost_minutes

    def hold(self, cm: Commitment) -> None:
        cm.status = Status.HELD
        cm.log(f"held: reviewer {self.reviewer_id} has {self.remaining}m left, "
               f"this needs {cm.review_cost_minutes}m")
        if cm.id not in self.held:
            self.held.append(cm.id)

    def summary(self) -> str:
        return (f"{self.reviewer_id}: {self.spent}m spent, {self.committed}m in flight, "
                f"{self.remaining}m free of {self.minutes_per_day}m")
