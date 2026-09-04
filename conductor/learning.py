"""Self-improvement: verified outcomes become the signal the system learns from.

A check passing says the work was correct; an outcome holding says the work
mattered. This memory records, per metric, how often a shipped outcome actually
held versus regressed after we believed it — the strongest signal Conductor has,
because it is reality's verdict, not a proxy. It feeds the confidence Conductor
reports and, over time, which plans and agents it reaches for. Derived from the
durable log, so it survives a restart.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class OutcomeMemory:
    held: dict = field(default_factory=lambda: defaultdict(int))       # metric -> times it held
    regressed: dict = field(default_factory=lambda: defaultdict(int))  # metric -> times it regressed

    def record(self, metric: str, held: bool) -> None:
        (self.held if held else self.regressed)[metric or "_"] += 1

    def rate(self, metric: str | None = None) -> float | None:
        if metric is not None:
            h, r = self.held.get(metric, 0), self.regressed.get(metric, 0)
        else:
            h, r = sum(self.held.values()), sum(self.regressed.values())
        n = h + r
        return round(h / n, 3) if n else None

    def summary(self) -> dict:
        return {"held": sum(self.held.values()),
                "regressed": sum(self.regressed.values()),
                "hold_rate": self.rate()}


def attach(conductor) -> OutcomeMemory:
    mem = getattr(conductor, "_outcome_memory", None)
    if mem is None:
        mem = conductor._outcome_memory = OutcomeMemory()
    return mem
