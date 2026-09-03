"""AgentCore Runtime entrypoint.

Conductor is not a request-response agent. It is a control loop that keeps
running between invocations, which is why this uses AgentCore's async task
support rather than answering and exiting: the runtime reports itself busy
while the loop verifies, recovers, speculates and dispatches in the background.

Invocations are how a human joins the loop, not how it starts.

    agentcore create --name Conductor --framework Strands --model-provider Bedrock
    agentcore dev
    agentcore deploy
    agentcore invoke '{"action": "state"}'
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

from conductor.world import build  # noqa: E402

app = BedrockAgentCoreApp()
C = build()


def _state() -> dict:
    return {
        "commitments": [
            {"id": c.id, "title": c.title, "status": c.status.value,
             "owner": c.owner, "risk": C.graph.score_risk(c),
             "speculative": bool(c.speculative_for)}
            for c in C.graph
        ],
        "decisions": [
            {"id": d.id, "question": d.root_question, "options": d.options,
             "unblocks": d.unblock_value, "compressed_from": len(d.merged_from) + 1}
            for d in C.surface.queue()
        ],
        "attention": [b.summary() for b in C.dispatcher.budgets.values()],
        "metrics": vars(C.metrics),
        "compression": C.surface.compression_ratio,
    }


@app.async_task
async def _background_loop(ticks: int) -> None:
    """Runs after the response is returned. The whole point of the product is
    that work continues while nobody is watching."""
    C.run(ticks=ticks)


@app.entrypoint
async def invoke(payload: dict) -> dict:
    """Actions:
      state    - the board, the decision queue, attention, metrics
      tick     - advance the loop n ticks synchronously
      run      - advance the loop in the background, return immediately
      answer   - spend attention: {"decision_id": ..., "choice": ...}
      plan     - natural language intent -> commitments carrying their own proof
      ask      - free-form question routed to the Strands orchestrator
    """
    action = (payload or {}).get("action", "state")

    if action == "state":
        return _state()

    if action == "tick":
        C.run(ticks=int(payload.get("ticks", 1)))
        return _state()

    if action == "run":
        await _background_loop(int(payload.get("ticks", 12)))
        return {"started": True, **_state()}

    if action == "answer":
        C.answer(payload["decision_id"], payload["choice"])
        C.run(ticks=int(payload.get("ticks", 4)))
        return _state()

    if action == "plan":
        from conductor.agents import PlannerAgent
        planner = PlannerAgent()
        plan = planner.plan(payload["intent"])
        made, rejected = planner.to_commitments(plan)
        for cm in made:
            C.graph.add(cm)
        return {
            "goal": plan.goal,
            "added": [c.title for c in made],
            # A plan whose proofs are weak is rejected, not filed.
            "rejected_for_weak_evidence": rejected,
            "assumptions": plan.assumptions,
        }

    if action == "ask":
        from conductor.agents import build_orchestrator
        return {"answer": str(build_orchestrator(C)(payload["prompt"]))}

    return {"error": f"unknown action {action!r}"}


if __name__ == "__main__":
    app.run()
