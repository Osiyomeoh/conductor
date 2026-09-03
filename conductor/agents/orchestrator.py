"""Orchestrator.

Composes the specialists using the agents-as-tools pattern, and exposes the
deterministic core to the model as tools. The model may plan, diagnose and
phrase questions. It may not decide that something is done, spend a human's
attention, or push an action past the policy engine: those are tools it calls,
with verdicts it cannot override.
"""

from __future__ import annotations

from .base import model


def build_orchestrator(conductor):
    from strands import Agent, tool

    @tool
    def board() -> str:
        """Current state of every commitment, with status and risk."""
        rows = []
        for cm in conductor.graph:
            rows.append(f"{cm.id} [{cm.status.value}] risk={conductor.graph.score_risk(cm):.2f} "
                        f"{cm.title} (owner={cm.owner or '-'})")
        return "\n".join(rows) or "empty"

    @tool
    def decision_queue() -> str:
        """Open questions for the human, ranked by how much work each unblocks."""
        return "\n".join(f"{d.id} unblocks={d.unblock_value} {d.root_question} "
                         f"options={d.options}" for d in conductor.surface.queue()) or "empty"

    @tool
    def attention_state() -> str:
        """How much review capacity each human has left today."""
        return "\n".join(b.summary() for b in conductor.dispatcher.budgets.values()) or "none"

    @tool
    def trust_state(worker_id: str) -> str:
        """What this worker has actually earned, per kind of work."""
        return conductor.trust.summary_line(worker_id)

    @tool
    def run_tick() -> str:
        """Advance the control loop one tick: verify, recover, compress,
        speculate, dispatch. Returns the events it produced."""
        before = len(conductor.events)
        conductor.tick()
        return "\n".join(conductor.events[before:]) or "no events"

    @tool
    def verify_now(commitment_id: str) -> str:
        """Run a commitment's evidence check. This is the ONLY way anything
        becomes done: the model cannot assert completion."""
        cm = conductor.graph.get(commitment_id)
        passed = conductor.verifier.verify(cm)
        return f"{'PASS' if passed else 'FAIL'}: {cm.evidence.detail}"

    return Agent(
        model=model("orchestrator"),
        name="conductor",
        description="Runs the project: plans, dispatches, verifies, replans, escalates",
        system_prompt=(
            "You run a project staffed by humans and AI agents.\n\n"
            "Two rules govern everything you do:\n"
            "1. `done` is a claim, not a fact. You may never mark work complete. "
            "Only `verify_now` can, and its verdict is final.\n"
            "2. Human attention is the scarce resource. Before proposing work, "
            "check `attention_state`. Holding work back is a valid and often "
            "correct decision.\n\n"
            "Be silent unless a real judgment call is needed. Status is not news."
        ),
        tools=[board, decision_queue, attention_state, trust_state, run_tick, verify_now],
    )
