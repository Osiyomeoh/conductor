"""The agent marketplace: hire specialists rated by verified track record.

Agents are hired, not configured, and the marketplace is where you pick one. A
listing is not marketing copy: each agent kind is rated by the work it has
actually passed on this team, so trust is earned and visible, never claimed.
Hiring from here goes through the same path as a hiring proposal.
"""

from __future__ import annotations

CATALOG = [
    {"kind": "code", "name": "impl-agent",
     "purpose": "Writes and fixes code, checked by a real test."},
    {"kind": "research", "name": "research-agent",
     "purpose": "Competitive and technical research, checked against a required document."},
    {"kind": "migration", "name": "migration-agent",
     "purpose": "Schema and data migrations, checked against the schema test."},
    {"kind": "content", "name": "docs-agent",
     "purpose": "Docs and copy, checked against a copy test."},
    {"kind": "test", "name": "test-agent",
     "purpose": "Writes tests that actually fail on the bug before they pass."},
    {"kind": "review", "name": "review-agent",
     "purpose": "Reviews changes against a checklist, and can rule a check wrong."},
]


def _rating_for_kind(conductor, kind: str) -> dict:
    """The team's verified track record for a kind of work: aggregate pass rate
    and job count across every agent that does it. Unproven kinds are rated None,
    which is honest, not zero."""
    passes = failures = 0
    for r in conductor.graph.resources.values():
        if kind in getattr(r, "skills", []):
            rec = conductor.trust.get(r.id, kind)
            passes += rec.passes
            failures += rec.failures
    total = passes + failures
    return {"verified_jobs": total,
            "pass_rate": round(passes / total, 3) if total else None}


def _has_agent_for(conductor, kind: str) -> bool:
    from .models import ResourceType
    return any(r.type is ResourceType.AGENT and kind in getattr(r, "skills", [])
               for r in conductor.graph.resources.values())


def listing(conductor) -> list[dict]:
    out = []
    for e in CATALOG:
        rating = _rating_for_kind(conductor, e["kind"])
        out.append({**e, **rating, "on_team": _has_agent_for(conductor, e["kind"])})
    # Rank by track record: proven first, then by pass rate, then by demand.
    return sorted(out, key=lambda a: (a["pass_rate"] is None, -(a["pass_rate"] or 0),
                                      -a["verified_jobs"]))
