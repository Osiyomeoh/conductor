"""Goal-to-plan derivation: you set the goal, Conductor derives the work.

At 1000x you don't describe a sprint; you state a goal, the metric that proves
it, and the values that bound it. Conductor reads where the metric is now,
proposes the work that would move it (each commitment with its own check), and
attaches the goal's metric itself as an OUTCOME commitment, so the sprint is not
done until reality moved and held (Phase A). The values ride into the plan as
constraints, so work that touches money or production is escalated, not run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Goal:
    intent: str
    outcome: str = ""                     # metric spec, e.g. "onboarding_completion >= 0.4"
    values: list = field(default_factory=list)   # bounding constraints


def _context(goal: Goal, metric_source) -> str:
    """The planner's brief: the goal, where the metric stands now, and the values."""
    gap = ""
    if goal.outcome and metric_source is not None:
        from .metrics import parse_outcome
        p = parse_outcome(goal.outcome)
        if p:
            metric, op, target = p
            v = metric_source.value(metric)
            here = f"{v}" if v is not None else "unknown"
            gap = f" Current {metric}={here}; target {op} {target}."
    values = (" Constraints: " + "; ".join(goal.values) + ".") if goal.values else ""
    return (f"Goal: {goal.intent}.{gap}{values} "
            f"Propose the work that moves this metric, each item with the check that proves it.")


def derive(goal: Goal, live: bool = False, metric_source=None):
    """Turn a goal into commitments: the work that should move the metric, plus
    the outcome commitment that is only done when the metric actually hits its
    target. Returns (commitments, rejected, source)."""
    from .models import Commitment, Evidence, EvidenceKind
    from .planning import plan_commitments
    made, rejected, source, _plan = plan_commitments(_context(goal, metric_source), live=live)
    if goal.outcome:
        outcome = Commitment.new(
            f"Reach the goal: {goal.intent}"[:120],
            Evidence(EvidenceKind.OUTCOME, spec=goal.outcome,
                     description="the goal's metric must hit its target and hold"),
            work_kind="outcome", review_cost_minutes=0)
        # Not consequential and not dispatched: reality confirms it, not a person
        # and not a worker. The loop watches it until the metric holds.
        made = list(made) + [outcome]
    return made, rejected, source
