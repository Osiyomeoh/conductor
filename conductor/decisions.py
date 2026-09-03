"""Decisions as first-class objects, and decision compression.

The other tools' idea of respecting your attention is a shorter notification
list. The real problem is that nine escalations usually share two underlying
uncertainties, and you answer the same thing nine times wearing different hats.

Conductor clusters escalations by the uncertainty behind them, asks the root
question once, and propagates the answer to every commitment that depended on
it. Questions are ranked by how much work each answer unblocks, so attention
is spent in value order.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Decision:
    id: str
    root_question: str
    options: list[str]
    uncertainty_key: str                    # what makes these the same question
    blocked: list[str] = field(default_factory=list)   # commitment ids
    merged_from: list[str] = field(default_factory=list)
    answer: str | None = None
    unblock_value: int = 0

    @staticmethod
    def new(question: str, options: list[str], key: str) -> "Decision":
        return Decision(id=f"dec_{uuid.uuid4().hex[:6]}", root_question=question,
                        options=options, uncertainty_key=key)


class DecisionSurface:
    """The only thing the human ever looks at. Usually empty."""

    def __init__(self, graph=None):
        self.open: dict[str, Decision] = {}
        self.answered: list[Decision] = []
        self.graph = graph

    def raise_question(self, question: str, options: list[str], key: str,
                       commitment_id: str) -> Decision:
        # Compression: an open decision with the same uncertainty absorbs this.
        for d in self.open.values():
            if d.uncertainty_key == key:
                if commitment_id not in d.blocked:
                    d.blocked.append(commitment_id)
                d.merged_from.append(commitment_id)
                self._rank(d)
                return d
        d = Decision.new(question, options, key)
        d.blocked.append(commitment_id)
        self.open[d.id] = d
        self._rank(d)
        return d

    def _rank(self, d: Decision) -> None:
        if self.graph is None:
            d.unblock_value = len(d.blocked)
            return
        total = 0
        for cid in d.blocked:
            total += 1 + self.graph.blocking_count(cid)
        d.unblock_value = total

    def queue(self) -> list[Decision]:
        return sorted(self.open.values(), key=lambda d: d.unblock_value, reverse=True)

    def answer(self, decision_id: str, choice: str) -> Decision:
        d = self.open.pop(decision_id)
        d.answer = choice
        self.answered.append(d)
        return d

    @property
    def open_ended(self) -> list["Decision"]:
        """Questions we cannot yet offer options for. These are the ones a
        human must frame, and the ones speculation cannot help with."""
        return [d for d in self.open.values() if len(d.options) < 2]

    @property
    def compression_ratio(self) -> str:
        raised = sum(len(d.merged_from) + 1 for d in list(self.open.values()) + self.answered)
        asked = len(self.open) + len(self.answered)
        return f"{raised} escalations compressed to {asked} questions" if asked else "no escalations"
