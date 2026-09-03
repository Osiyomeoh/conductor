"""Cost accounting.

Conductor deliberately spends compute to save attention. That argument only
holds if the spending is visible and small. An unmeasured claim that
speculation is "cheap" is exactly the kind of assertion a buyer discounts, so
every dispatch is priced and attributed.

Two numbers matter more than the total:

  cost per VERIFIED commitment   what the customer actually got
  cost burned on REJECTED claims what the verification layer saved them from
                                 reviewing by hand

The second is the product's whole case, in money.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# USD per million tokens. Placeholders until measured against a real bill.
PRICES: dict[str, tuple[float, float]] = {
    "global.anthropic.claude-sonnet-4-6": (3.00, 15.00),
    "default": (3.00, 15.00),
}


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, PRICES["default"])
    return (input_tokens / 1e6) * pin + (output_tokens / 1e6) * pout


@dataclass
class Entry:
    commitment_id: str
    worker: str
    model: str
    input_tokens: int
    output_tokens: int
    usd: float
    branch: str | None = None
    decision_id: str | None = None
    outcome: str = "pending"       # verified | rejected | discarded | pending


@dataclass
class CostLedger:
    entries: list[Entry] = field(default_factory=list)

    def record(self, cm, worker: str, model: str, input_tokens: int,
               output_tokens: int) -> Entry:
        e = Entry(commitment_id=cm.id, worker=worker, model=model,
                  input_tokens=input_tokens, output_tokens=output_tokens,
                  usd=price(model, input_tokens, output_tokens),
                  branch=cm.branch, decision_id=cm.speculative_for)
        self.entries.append(e)
        return e

    def settle(self, commitment_id: str, outcome: str) -> None:
        """Attach the verdict to everything spent on this commitment.

        `discarded` overrides an earlier verdict: work on a losing branch may
        well have passed its check, but the human chose another answer, so the
        money went on something nobody will ever use. Reporting it as verified
        spend would flatter the speculation argument, which is the one number
        that has to be honest.
        """
        for e in self.entries:
            if e.commitment_id != commitment_id:
                continue
            if e.outcome == "pending" or outcome == "discarded":
                e.outcome = outcome

    # -- views ----------------------------------------------------------
    @property
    def total(self) -> float:
        return sum(e.usd for e in self.entries)

    def by_outcome(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.entries:
            out[e.outcome] = out.get(e.outcome, 0.0) + e.usd
        return out

    def for_decision(self, decision_id: str) -> float:
        return sum(e.usd for e in self.entries if e.decision_id == decision_id)

    def for_branch(self, branch: str) -> float:
        return sum(e.usd for e in self.entries if e.branch == branch)

    def cost_per_verified(self) -> float:
        n = len({e.commitment_id for e in self.entries if e.outcome == "verified"})
        return self.total / n if n else 0.0

    def wasted_on_rejected(self) -> float:
        return self.by_outcome().get("rejected", 0.0)

    def summary(self) -> str:
        b = self.by_outcome()
        return (f"${self.total:.4f} total | "
                f"${b.get('verified', 0):.4f} on verified | "
                f"${b.get('rejected', 0):.4f} on rejected | "
                f"${b.get('discarded', 0):.4f} on discarded branches")
