"""Core domain model.

Two ideas carry this whole system:

  1. `done` is a claim, not a fact. Every Commitment declares, at plan time,
     the Evidence that must pass before it may be believed. Agents report
     success confidently and wrongly; humans do too, more rarely.

  2. Human attention is the scarce resource, not worker time. Agent labour is
     cheap and parallel; the reviewer is neither. Dispatch spends against a
     reviewer's budget, and when the budget is gone, work waits.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


def now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class ResourceType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


class Status(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    CLAIMED_DONE = "claimed_done"   # worker says finished; unverified
    VERIFYING = "verifying"
    DONE = "done"                   # evidence passed
    REJECTED = "rejected"           # evidence failed; back to the worker
    BLOCKED = "blocked"
    AT_RISK = "at_risk"
    HELD = "held"                   # ready, but no review capacity to absorb it
    ESCALATED = "escalated"


class EvidenceKind(str, Enum):
    COMMAND = "command"       # a shell command must exit 0
    FILE_EXISTS = "file"      # a path must exist and be non-empty
    HTTP_OK = "http"          # an endpoint must respond
    CI = "ci"                 # the repo's own CI must pass (resolved async by webhook)
    OUTCOME = "outcome"       # a real metric must hit its target (verify reality, not work)
    HUMAN_REVIEW = "review"   # only a person can confirm this one
    NONE = "none"             # unverifiable; treated as a planning defect


class Decision(str, Enum):
    AUTO = "auto"
    APPROVE = "approve"
    BLOCK = "block"


@dataclass
class Evidence:
    """What must be true for a claim of completion to be believed."""
    kind: EvidenceKind
    spec: str = ""
    description: str = ""
    # Set by the verification runner.
    passed: bool | None = None
    detail: str = ""
    checked_at: datetime | None = None

    @property
    def machine_checkable(self) -> bool:
        return self.kind in (EvidenceKind.COMMAND, EvidenceKind.FILE_EXISTS, EvidenceKind.HTTP_OK)


@dataclass
class Resource:
    """A worker. Humans and agents are the same kind of thing here, with
    different reliability curves and, crucially, different review costs."""
    id: str
    type: ResourceType
    name: str
    skills: list[str] = field(default_factory=list)
    capacity_hours_per_day: float = 6.0
    # Rolling outcome-derived score: fraction of claims that survived verification.
    claims: int = 0
    claims_verified: int = 0
    timezone: str = "UTC"
    channel: str = "none"
    # An agent may act FOR a person. It inherits that principal's scopes, never
    # exceeds them, and its work is reviewed by that principal by default.
    principal: str | None = None
    # What this worker is permitted to touch. The policy engine reads these.
    scopes: list[str] = field(default_factory=list)
    # Agents only: how to actually run one.
    spec: "AgentSpec | None" = None
    probation: bool = True

    @property
    def reliability(self) -> float:
        if self.claims == 0:
            return 0.7 if self.type is ResourceType.AGENT else 0.85
        return self.claims_verified / self.claims

    def record_claim(self, verified: bool) -> None:
        self.claims += 1
        if verified:
            self.claims_verified += 1


@dataclass
class Commitment:
    """A node in the commitment graph. Not a ticket: it carries its own
    definition of proof, its reviewer, and the attention it will cost."""
    id: str
    title: str
    evidence: Evidence
    owner: str | None = None
    reviewer: str | None = None          # who spends attention on this
    dependencies: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    status: Status = Status.PENDING
    # Minutes of human attention this will cost to review once claimed.
    review_cost_minutes: int = 10
    # The planner's estimate. Trust scales the effective cost from THIS, never
    # from the last value, or repeated deep checks compound: 40 -> 80 -> 640.
    base_review_cost: int | None = None
    consequential: bool = False          # touches users, money, or prod
    ambiguous: bool = False              # needs judgment, not execution
    attempts: int = 0
    recovery_stage: int = 0
    last_signal: datetime = field(default_factory=now)
    # Isolation: agent work never touches shared state until evidence passes.
    branch: str | None = None
    # Speculation: this commitment exists only if `assumes` turns out true.
    speculative_for: str | None = None
    assumes: dict = field(default_factory=dict)
    work_kind: str = "general"
    # Demo/exec substrate: where the worker's output lands, and the token that
    # proves the asked-for thing is actually present.
    artifact_path: str | None = None
    expected_token: str = "OK"
    options: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    notes: str = ""

    @staticmethod
    def new(title: str, evidence: Evidence, **kw) -> "Commitment":
        return Commitment(id=_id("cm"), title=title, evidence=evidence, **kw)

    def log(self, msg: str) -> None:
        self.history.append(f"{now().isoformat(timespec='seconds')}  {msg}")

    @property
    def silent_for(self) -> timedelta:
        return now() - self.last_signal

    @property
    def terminal(self) -> bool:
        return self.status is Status.DONE


@dataclass
class Action:
    """Anything Conductor wants to do to the world. Everything routes through
    the policy engine before it happens."""
    kind: str                      # dispatch | message | reassign | escalate | replan | verify
    commitment_id: str | None
    summary: str
    payload: dict = field(default_factory=dict)
    irreversible: bool = False
    external: bool = False         # leaves the system: email, Slack, PR, customer
    cost_estimate: float = 0.0


@dataclass
class PolicyVerdict:
    decision: Decision
    risk: float
    reasons: list[str]
