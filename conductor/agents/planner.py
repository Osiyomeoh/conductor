"""Planner agent.

The hardest judgment in the whole system is not decomposition. Any model can
split a goal into tasks. It is writing, for each task, the check that actually
proves the task was done, and being honest about which tasks no machine can
check. A weak evidence requirement is worse than none, because it launders a
false claim into a green tick.

So the Planner is required to emit evidence with every commitment, and the
deterministic `evidence_quality` gate rejects its plan if the proof is trivial.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import Commitment, Evidence, EvidenceKind
from ..verification import evidence_quality
from .base import model

SYSTEM = """You plan work for a team of humans and AI agents.

For every commitment you must state the evidence that proves it is done. This
is the most important part of your job. Rules:

- Prefer a `command` whose failure is meaningful: a test that fails without the
  change, a script that exits non-zero when the thing is missing. Never `true`,
  never `echo ok`, never a command that passes on an empty repo.
- Use `file` only when existence genuinely proves the work.
- Use `review` ONLY when no machine check could establish it: taste, strategy,
  wording, product judgment. Do not reach for it to avoid thinking.
- Never emit `none`.

Also classify each commitment:
- ambiguous: it is a judgment call, not execution. These become questions for a
  human, never tasks. Give the plausible options.
- consequential: touches production, money, or customers.
- work_kind: short slug, e.g. code, research, content, design, product.
- review_cost_minutes: honest estimate of the human time to check the result.

Assume agent labour is free and parallel, and that the human's attention is the
only scarce resource. Plan accordingly: prefer many small checkable units over
few large unverifiable ones."""


class PlannedCommitment(BaseModel):
    title: str
    evidence_kind: str = Field(description="command | file | http | review")
    evidence_spec: str = Field(default="", description="the command, path or url")
    evidence_description: str = ""
    work_kind: str = "general"
    review_cost_minutes: int = 10
    ambiguous: bool = False
    consequential: bool = False
    options: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list,
                                  description="titles of prerequisite commitments")


class SprintPlan(BaseModel):
    goal: str
    commitments: list[PlannedCommitment]
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class PlannerAgent:
    def __init__(self, temperature: float = 0.2):
        from strands import Agent
        self.agent = Agent(model=model("planner"), system_prompt=SYSTEM,
                           name="planner",
                           description="Turns intent into commitments that carry their own proof")

    def plan(self, intent: str) -> SprintPlan:
        return self.agent.structured_output(SprintPlan, intent)

    def to_commitments(self, plan: SprintPlan) -> tuple[list[Commitment], list[str]]:
        """Materialise the plan, refusing any commitment whose proof is weak."""
        made: dict[str, Commitment] = {}
        rejected: list[str] = []
        for pc in plan.commitments:
            kind = {"command": EvidenceKind.COMMAND, "file": EvidenceKind.FILE_EXISTS,
                    "http": EvidenceKind.HTTP_OK, "review": EvidenceKind.HUMAN_REVIEW,
                    }.get(pc.evidence_kind.lower(), EvidenceKind.NONE)
            ev = Evidence(kind, spec=pc.evidence_spec, description=pc.evidence_description)
            ok, why = evidence_quality(ev)
            if not ok:
                rejected.append(f"{pc.title}: {why}")
                continue
            cm = Commitment.new(pc.title, ev, work_kind=pc.work_kind,
                                review_cost_minutes=pc.review_cost_minutes,
                                ambiguous=pc.ambiguous, consequential=pc.consequential,
                                options=pc.options)
            made[pc.title] = cm
        for pc in plan.commitments:
            if pc.title in made:
                made[pc.title].dependencies = [made[d].id for d in pc.depends_on if d in made]
        return list(made.values()), rejected
