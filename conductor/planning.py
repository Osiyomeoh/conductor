"""Turning a spoken intent into a reviewable plan.

Uses the live Planner agent when Bedrock is reachable, and otherwise a fixture
that mirrors what the agent produces. Both paths run through the SAME evidence
gate, so the "rejected by the planner" list is genuinely computed rather than
scripted: a fixture cannot fake its way past evidence_quality.
"""

from __future__ import annotations

from .agents.planner import PlannedCommitment, SprintPlan, materialise

DEMO_INTENT = (
    "Next sprint I need the onboarding flow redesigned, the payment webhook "
    "fixed, and competitive research on three tools. Sarah owns design, agents "
    "can handle the research and the webhook tests."
)


def _fixture(intent: str) -> SprintPlan:
    """A realistic plan, including two commitments whose proof is too weak to
    survive the gate. The weak ones are the point: they show the planner
    refusing to plan work whose completion could not be proven."""
    pc = PlannedCommitment
    return SprintPlan(
        goal=intent,
        commitments=[
            pc(title="Fix the payment webhook retry", evidence_kind="command",
               evidence_spec="pytest tests/test_webhook_retry.py",
               work_kind="code", review_cost_minutes=20),
            pc(title="Add webhook regression tests", evidence_kind="command",
               evidence_spec="pytest tests/test_webhook_regression.py",
               work_kind="code", review_cost_minutes=15,
               depends_on=["Fix the payment webhook retry"]),
            pc(title="Competitive research on three tools", evidence_kind="file",
               evidence_spec="research/competitors.md",
               work_kind="research", review_cost_minutes=10),
            pc(title="Migrate the onboarding events table", evidence_kind="command",
               evidence_spec="alembic upgrade head && pytest tests/test_events_schema.py",
               work_kind="code", review_cost_minutes=25, consequential=True),
            pc(title="Rewrite onboarding empty states", evidence_kind="command",
               evidence_spec="pytest tests/test_copy.py", work_kind="content",
               review_cost_minutes=10),
            pc(title="Decide the onboarding paywall position", evidence_kind="review",
               work_kind="product", review_cost_minutes=30, ambiguous=True,
               options=["paywall after first value moment", "paywall on signup",
                        "no paywall, usage limit instead"]),
            pc(title="Redesign the onboarding flow", evidence_kind="review",
               work_kind="design", review_cost_minutes=30, ambiguous=True,
               depends_on=["Decide the onboarding paywall position"]),
            # These two are refused by the gate, on purpose.
            pc(title="Improve onboarding", evidence_kind="none",
               work_kind="product", review_cost_minutes=20),
            pc(title="Tidy up the codebase", evidence_kind="command",
               evidence_spec="true", work_kind="code", review_cost_minutes=10),
        ],
        assumptions=["Sarah is available for design this sprint"],
    )


import os


def live_available() -> bool:
    """Live planning only when a provider is actually reachable. Gemini needs a
    key; Bedrock is opt-in via CONDUCTOR_LIVE_PLAN=1 so the app does not hang on
    a throttled default. Otherwise the planner uses the fixture, instantly."""
    if os.environ.get("CONDUCTOR_PROVIDER", "bedrock") == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return os.environ.get("CONDUCTOR_LIVE_PLAN") == "1"


def plan_commitments(intent: str, live: bool):
    """Return (real Commitment objects, rejected, source) for an intent."""
    source = "fixture"
    plan = _fixture(intent)
    if live:
        try:
            from .agents.planner import PlannerAgent
            plan = PlannerAgent().plan(intent)
            source = "planner-agent"
        except Exception:
            plan = _fixture(intent); source = "fixture"
    made, rejected = materialise(plan)
    return made, rejected, source, plan


def propose(intent: str | None = None, live: bool = False) -> dict:
    intent = intent or DEMO_INTENT
    made, rejected, source, plan = plan_commitments(intent, live)
    by_title = {c.title: c for c in made}
    order = [pc.title for pc in plan.commitments]

    commitments = []
    for title in order:
        cm = by_title.get(title)
        if cm is None:
            continue
        commitments.append({
            "title": cm.title,
            "proof": cm.evidence.spec or cm.evidence.description or "human review",
            "proof_kind": cm.evidence.kind.value,
            "work_kind": cm.work_kind,
            "review_cost": cm.review_cost_minutes,
            "judgment": cm.ambiguous,
            "consequential": cm.consequential,
            "depends_on": [by_title_id.title for by_title_id in made
                           if by_title_id.id in cm.dependencies],
            "options": cm.options,
        })

    return {
        "intent": intent,
        "goal": plan.goal,
        "source": source,
        "commitments": commitments,
        "rejected": [{"title": t, "reason": w} for t, w in rejected],
        "assumptions": plan.assumptions,
    }
