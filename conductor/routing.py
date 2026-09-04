"""Judgment routing: the one decision to the one right person.

The trust ledger prices what an agent has earned per kind of work. This does the
same for people: it learns who has actually answered decisions in a domain well,
so when a question surfaces it can be routed to the person whose judgment it is,
not round-robined to whoever is free. Expertise is earned, like trust, and shown,
never assumed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ExpertiseLedger:
    scores: dict = field(default_factory=dict)     # (subject, domain) -> weight

    def record(self, subject: str, domain: str, weight: float = 1.0) -> None:
        if subject and domain:
            self.scores[(subject, domain)] = self.scores.get((subject, domain), 0.0) + weight

    def score(self, subject: str, domain: str) -> float:
        return self.scores.get((subject, domain), 0.0)

    def best_for(self, domain: str, candidates=None) -> str | None:
        rows = [(s, v) for (s, d), v in self.scores.items()
                if d == domain and (candidates is None or s in candidates)]
        if not rows:
            return None
        return max(rows, key=lambda r: r[1])[0]


def attach(conductor) -> ExpertiseLedger:
    """The per-conductor expertise ledger, created lazily. Kept off the dataclass
    so it never has to survive replay: expertise is derived from decisions, and
    those are in the durable log."""
    led = getattr(conductor, "expertise", None)
    if led is None:
        led = conductor.expertise = ExpertiseLedger()
    return led


def decision_domain(graph, decision) -> str:
    """The domain a decision is about: the dominant kind of work it unblocks."""
    kinds = Counter()
    for cid in getattr(decision, "blocked", []) or []:
        cm = graph.get(cid)
        if cm is not None:
            kinds[cm.work_kind] += 1
    return kinds.most_common(1)[0][0] if kinds else "general"
