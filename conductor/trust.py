"""Trust ledger.

Verification costs time and compute. Verifying everything forever is how a
control system ends up slower than the humans it replaced. So trust is earned
per worker per kind of work, from outcomes only, and it prices how deep the
next check has to be.

Trust rises slowly and falls immediately. That asymmetry is deliberate: one
confident-and-wrong completion should cost a worker more than ten successes
earned it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrustRecord:
    passes: int = 0
    failures: int = 0
    streak: int = 0

    @property
    def score(self) -> float:
        n = self.passes + self.failures
        if n == 0:
            return 0.5
        # Laplace-smoothed, then penalised hard for any recent failure.
        base = (self.passes + 1) / (n + 2)
        return round(base * (0.55 if self.streak < 0 else 1.0), 3)


@dataclass
class TrustLedger:
    records: dict[tuple[str, str], TrustRecord] = field(default_factory=dict)

    def get(self, worker: str, kind: str) -> TrustRecord:
        return self.records.setdefault((worker, kind), TrustRecord())

    def peek(self, worker: str, kind: str) -> float:
        """Read a score without creating a record. Ranking must not write."""
        r = self.records.get((worker, kind))
        return r.score if r else 0.5

    def record(self, worker: str, kind: str, passed: bool) -> None:
        r = self.get(worker, kind)
        if passed:
            r.passes += 1
            r.streak = max(1, r.streak + 1)
        else:
            r.failures += 1
            r.streak = min(-1, r.streak - 1)

    def evidence_depth(self, worker: str, kind: str) -> str:
        """How hard the next check should be. Drives verification cost."""
        s = self.get(worker, kind).score
        if s >= 0.85:
            return "light"    # spot check
        if s >= 0.6:
            return "standard"
        return "deep"         # full check plus review

    def summary_line(self, worker: str) -> str:
        rows = [(k, r) for (w, k), r in self.records.items() if w == worker]
        if not rows:
            return f"{worker}: no history"
        return "  ".join(f"{k}={r.score:.0%}({r.passes}/{r.passes+r.failures})" for k, r in rows)
