"""AgentCore Runtime entrypoint.

The always-on service form is conductor.asgi (uvicorn). This is the invocation
form: AgentCore Runtime calls the handler, which joins the durable loop for the
caller's tenant. The loop keeps running between invocations via async_task, so
the runtime reports itself busy while it verifies, recovers and dispatches.

    agentcore invoke '{"action":"state"}'
    agentcore invoke '{"action":"run","ticks":6}'
    agentcore invoke '{"action":"answer","decision_id":"...","choice":"..."}'
"""

from __future__ import annotations

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from .config import CONFIG
from .registry import Registry
from .server import decision_detail, state
from .world import persistent

# Inside the runtime the task role is the identity; use ambient credentials.
os.environ.setdefault("CONDUCTOR_AWS_PROFILE", "")

app = BedrockAgentCoreApp()
registry = Registry(build_fn=lambda store, tenant: persistent(store=store, tenant=tenant))


@app.async_task
async def _advance(tenant: str, ticks: int) -> None:
    registry.write(tenant, lambda c: c.run(ticks=ticks))


@app.entrypoint
async def invoke(payload: dict) -> dict:
    payload = payload or {}
    tenant = payload.get("tenant", CONFIG.tenant)
    action = payload.get("action", "state")

    if action == "state":
        return registry.read(tenant, state)
    if action == "decision":
        return registry.read(tenant, lambda c: decision_detail(c, payload["id"]))
    if action == "tick":
        return registry.write(tenant,
            lambda c: (c.run(ticks=int(payload.get("ticks", 1))), state(c))[1])
    if action == "run":
        await _advance(tenant, int(payload.get("ticks", 12)))
        return {"started": True, **registry.read(tenant, state)}
    if action == "answer":
        def do(c):
            c.answer(payload["decision_id"], payload["choice"])
            c.run(ticks=4)
            return state(c)
        return registry.write(tenant, do)
    return {"error": f"unknown action {action!r}"}


if __name__ == "__main__":
    app.run()
