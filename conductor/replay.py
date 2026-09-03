"""Rebuilding state from the log.

If the graph can be reconstructed exactly from events, three things follow:
the loop is resumable, a run is auditable transition by transition, and a demo
can replay a real run without dispatching live agents at it.

Replay applies facts. It never re-runs verification, never calls a model, and
never spends money: those already happened, and their outcomes are in the log.
"""

from __future__ import annotations

from .events import Event, EventKind
from .models import Commitment, Evidence, EvidenceKind, Resource, ResourceType, Status

# What each recorded fact did to a commitment.
_STATUS = {
    EventKind.DISPATCHED: Status.DISPATCHED,
    EventKind.HELD: Status.HELD,
    EventKind.CLAIMED: Status.CLAIMED_DONE,
    EventKind.VERIFIED: Status.DONE,
    EventKind.REJECTED: Status.REJECTED,
    EventKind.ESCALATED: Status.ESCALATED,
    EventKind.DISCARDED: Status.BLOCKED,
    EventKind.BLOCKED: Status.ESCALATED,
}


def _recreate(graph, event: Event) -> None:
    """A PLANNED event carries everything needed to rebuild the node, so a
    replayed graph is constructed from facts rather than from a seed script."""
    d = event.data
    cm = Commitment(
        id=event.commitment_id,
        title=d.get("title", ""),
        evidence=Evidence(EvidenceKind(d.get("evidence_kind", "none")),
                          spec=d.get("evidence_spec", "")),
        work_kind=d.get("work_kind", "general"),
        review_cost_minutes=d.get("review_cost_minutes", 10),
        ambiguous=d.get("ambiguous", False),
        consequential=d.get("consequential", False),
        options=d.get("options", []) or [],
        dependencies=d.get("dependencies", []) or [],
        artifact_path=d.get("artifact_path"),
        expected_token=d.get("expected_token", "OK"),
        speculative_for=d.get("speculative_for"),
        branch=d.get("branch"))
    graph.commitments[cm.id] = cm


def _rehire(graph, event: Event) -> None:
    d = event.data
    graph.resources[event.actor] = Resource(
        id=event.actor, type=ResourceType(d.get("type", "agent")),
        name=d.get("name", event.actor), skills=d.get("skills", []) or [],
        principal=d.get("principal"), scopes=d.get("scopes", []) or [])


def apply(graph, event: Event) -> None:
    if event.kind is EventKind.PLANNED:
        _recreate(graph, event)
        return
    if event.kind is EventKind.HIRED:
        _rehire(graph, event)
        return
    cid = event.commitment_id
    if cid is None or cid not in graph.commitments:
        return
    cm = graph.get(cid)
    status = _STATUS.get(event.kind)
    if status is not None:
        cm.status = status
    if event.kind is EventKind.VERIFIED:
        cm.evidence.passed = True
        cm.evidence.detail = event.data.get("detail", "")
    elif event.kind is EventKind.REJECTED:
        cm.evidence.passed = False
        cm.evidence.detail = event.data.get("detail", "")
    if event.actor:
        cm.owner = event.actor
    if event.kind is EventKind.DISPATCHED:
        cm.attempts = event.data.get("attempt", cm.attempts)
    cm.history.append(f"{event.at}  replay:{event.kind.value}")


def rebuild(graph, events) -> int:
    """Fold the log over a graph, creating nodes as PLANNED events introduce
    them. Returns the sequence reached, which is where a resumed loop starts."""
    seq = 0
    for e in events:
        apply(graph, e)
        seq = max(seq, e.seq)
    return seq


def summarise(events) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind.value] = counts.get(e.kind.value, 0) + 1
    return counts
