"""The roster: hiring, delegation, and elastic headcount.

Three ideas here, and the third is the one that does not exist anywhere else.

1. An agent teammate is declared, not hardcoded. An AgentSpec is a job
   description: what it is for, what it may touch, what tools it has.

2. An agent can belong to a person. Sarah's agent acts for Sarah, inherits her
   scopes and never exceeds them, and its output is reviewed by Sarah by
   default. Delegation, with the accountability staying where it was.

3. Headcount is a control variable. When the graph is bottlenecked on a kind of
   work, Conductor can propose hiring an agent for it. You approve a teammate
   the way you approve a decision, and it starts on probation: deep verification
   on everything until it earns its way down. Exactly like a new hire, for
   exactly the same reason.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .models import Resource, ResourceType, Status


@dataclass
class AgentSpec:
    """A job description an agent can actually be run from."""
    purpose: str                                   # becomes the system prompt
    work_kinds: list[str]                          # what it is hired to do
    tools: list[str] = field(default_factory=list) # named tools it may call
    model: str | None = None
    scopes: list[str] = field(default_factory=list)
    max_parallel: int = 4
    notes: str = ""


@dataclass
class Roster:
    graph: object
    trust: object

    # -- hiring ---------------------------------------------------------
    def hire(self, agent_id: str, name: str, spec: AgentSpec,
             principal: str | None = None) -> Resource:
        """Add an agent to the team. It starts on probation with no trust, so
        every claim is deep-verified until it earns otherwise."""
        scopes = list(spec.scopes)
        if principal:
            p = self.graph.resources.get(principal)
            if p is None:
                raise ValueError(f"unknown principal {principal!r}")
            # An agent can never hold a scope its principal does not have.
            scopes = [s for s in scopes if s in p.scopes] or list(p.scopes)
        r = Resource(id=agent_id, type=ResourceType.AGENT, name=name,
                     skills=list(spec.work_kinds), principal=principal,
                     scopes=scopes, spec=spec, probation=True)
        return self.graph.add_resource(r)

    def graduate(self, agent_id: str, min_passes: int = 5) -> bool:
        """Probation ends on evidence, not on time served."""
        r = self.graph.resources[agent_id]
        rec = [self.trust.get(agent_id, k) for k in r.skills]
        passes = sum(x.passes for x in rec)
        failures = sum(x.failures for x in rec)
        if passes >= min_passes and failures == 0:
            r.probation = False
        return not r.probation

    # -- elastic headcount ----------------------------------------------
    def bottlenecks(self, min_waiting: int = 3) -> list[tuple[str, int]]:
        """Kinds of work with a queue and nobody good at them."""
        # Judgment work is never a hiring signal. A queue of decisions means
        # the human is the bottleneck, and hiring an agent for it would route
        # exactly the work that must not be automated.
        waiting = Counter(
            cm.work_kind for cm in self.graph
            if cm.status in (Status.PENDING, Status.HELD, Status.REJECTED)
            and not cm.ambiguous and not cm.consequential)
        out = []
        for kind, n in waiting.items():
            capable = [r for r in self.graph.resources.values() if kind in r.skills]
            best = max((self.trust.peek(r.id, kind) for r in capable), default=0.0)
            if n >= min_waiting and (not capable or best < 0.6):
                out.append((kind, n))
        return sorted(out, key=lambda x: -x[1])

    def propose_hire(self, kind: str, count: int) -> dict:
        """A hiring request, phrased as a decision for a human. Adding a
        teammate is consequential, so it is never automatic."""
        return {
            "question": f"{count} items are queued on '{kind}' and nobody on the "
                        f"team is reliable at it. Add an agent for it?",
            "options": [f"hire a {kind} agent", "reassign to a human",
                        "leave it queued"],
            "uncertainty_key": f"headcount:{kind}",
            "spec": AgentSpec(
                purpose=f"Handle {kind} work end to end, and produce output whose "
                        f"correctness can be checked mechanically.",
                work_kinds=[kind], scopes=["repo:read", "repo:write:branch"]),
        }

    # -- delegation ------------------------------------------------------
    def delegates_of(self, human_id: str) -> list[Resource]:
        return [r for r in self.graph.resources.values() if r.principal == human_id]

    def reviewer_for(self, worker_id: str) -> str | None:
        """An agent's work goes back to the person it acts for. Delegation
        moves the labour, not the accountability."""
        r = self.graph.resources.get(worker_id)
        if r is None:
            return None
        return r.principal or None
