"""Production ASGI application.

Replaces the demo http.server with a FastAPI app that carries the production
concerns as first-class middleware and dependencies:

  - per-tenant conductors (registry), so tenants are isolated and concurrent
  - an auth boundary that resolves the caller to a tenant (demo or enforced)
  - request logging with timing and a request id (observability)
  - durable state: each tenant resumes from its own log

Run: uvicorn conductor.asgi:app --host 0.0.0.0 --port 7616
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .auth import Principal, auth_required, mint_session, principal_from
from .config import CONFIG
from .registry import Registry
from .server import LANDING, ONBOARDING, UI, UI_DIR, activity, decision_detail, state, team
from .world import persistent

log = logging.getLogger("conductor.asgi")

# The React + TypeScript app, built to web/dist, is served at /app when present.
# Falls back to the hand-rolled vanilla page if the frontend has not been built.
import os
_WEB_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
_REACT_INDEX = os.path.join(_WEB_DIST, "index.html")
_REACT_BUILT = os.path.isfile(_REACT_INDEX)

app = FastAPI(title="Conductor", version="1.0")
registry = Registry(build_fn=lambda store, tenant: persistent(store=store, tenant=tenant))


@app.middleware("http")
async def observe(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    start = time.perf_counter()
    request.state.rid = rid
    try:
        response = await call_next(request)
    except Exception:
        log.exception("rid=%s %s %s failed", rid, request.method, request.url.path)
        return JSONResponse({"error": "internal error", "request_id": rid}, status_code=500)
    ms = (time.perf_counter() - start) * 1000
    log.info("rid=%s %s %s -> %d %.1fms", rid, request.method, request.url.path,
             response.status_code, ms)
    response.headers["x-request-id"] = rid
    return response


def caller(request: Request) -> Principal:
    p = principal_from(request.headers, request.cookies)
    if p is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return p


# --- API -------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "provider": CONFIG.provider,
            "auth": "enforced" if auth_required() else "disabled",
            "tenants": registry.tenants()}


@app.get("/api/state")
def api_state(p: Principal = Depends(caller)):
    return registry.read(p.tenant, state)


@app.get("/api/team")
def api_team(p: Principal = Depends(caller)):
    return registry.read(p.tenant, team)


@app.get("/api/activity")
def api_activity(p: Principal = Depends(caller)):
    return registry.read(p.tenant, activity)


@app.get("/api/plan")
def api_plan(p: Principal = Depends(caller)):
    from .planning import propose
    return registry.read(p.tenant, lambda c: propose())


@app.get("/api/decision")
def api_decision(id: str, p: Principal = Depends(caller)):
    return registry.read(p.tenant, lambda c: decision_detail(c, id))


@app.post("/api/tick")
async def api_tick(request: Request, p: Principal = Depends(caller)):
    body = await _json(request)
    ticks = max(1, min(20, int(body.get("ticks", 1))))
    return registry.write(p.tenant, lambda c: (c.run(ticks=ticks), state(c))[1])


@app.post("/api/plan")
async def api_plan(request: Request, p: Principal = Depends(caller)):
    """Turn a spoken sprint into a reviewable plan. Uses the live Strands
    Planner when a provider is configured, and a fixture otherwise, both through
    the same evidence gate."""
    from .planning import live_available, propose
    body = await _json(request)
    intent = (body.get("intent") or "").strip() or None
    return propose(intent, live=live_available())


@app.post("/api/approve")
async def api_approve(request: Request, p: Principal = Depends(caller)):
    """Approve a planned sprint: materialise its commitments into the tenant's
    running conductor and start the loop. This is the whole arc, from one
    conversation to a team doing the work."""
    from .planning import live_available, plan_commitments
    body = await _json(request)
    intent = (body.get("intent") or "").strip()
    if not intent:
        raise HTTPException(status_code=400, detail="intent required")
    made, _rejected, source, _plan = plan_commitments(intent, live=live_available())

    def do(c):
        for cm in made:
            c.graph.add(cm)
        c.run(ticks=4)
        s = state(c)
        s["approved"] = len(made)
        s["planned_by"] = source
        return s
    return registry.write(p.tenant, do)


@app.post("/api/answer")
async def api_answer(request: Request, p: Principal = Depends(caller)):
    body = await _json(request)
    if "decision_id" not in body or "choice" not in body:
        raise HTTPException(status_code=400, detail="decision_id and choice required")

    def do(c):
        c.answer(body["decision_id"], body["choice"])
        c.run(ticks=4)
        return state(c)
    try:
        return registry.write(p.tenant, do)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown decision")


@app.post("/api/auth/session")
async def api_session(request: Request):
    """Prototype login: issue a session for a tenant. In production this runs
    only AFTER an identity provider has authenticated the user; it never
    accepts a password here."""
    if not auth_required():
        return {"note": "auth disabled; the demo tenant is used automatically"}
    body = await _json(request)
    tenant = body.get("tenant") or "default"
    subject = body.get("subject") or "user"
    token = mint_session(subject, tenant, body.get("email"))
    resp = JSONResponse({"tenant": tenant})
    resp.set_cookie("conductor_session", token, httponly=True, samesite="lax",
                    secure=True, max_age=86400)
    return resp


# --- static ----------------------------------------------------------------
@app.get("/shot/{name}")
def shot(name: str):
    import os
    path = os.path.join(os.path.dirname(UI_DIR), "..", "docs", "shots", os.path.basename(name))
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404)


@app.get("/assets/{asset:path}")
def react_assets(asset: str):
    """Serve the built React bundle's hashed, content-addressed assets."""
    path = os.path.join(_WEB_DIST, "assets", os.path.basename(asset))
    if _REACT_BUILT and os.path.isfile(path):
        return FileResponse(path, headers={"cache-control": "public, max-age=31536000, immutable"})
    raise HTTPException(status_code=404)


@app.get("/{path:path}", response_class=HTMLResponse)
def spa(path: str):
    """The React single-page app owns every HTML route — landing, onboarding
    and the app — and routes client-side. The hand-rolled vanilla pages remain
    the fallback only when the frontend has not been built."""
    if path.startswith("api") or path.startswith("shot") or path.startswith("assets"):
        raise HTTPException(status_code=404)
    if _REACT_BUILT:
        return HTMLResponse(open(_REACT_INDEX).read())
    if path in ("signup", "onboarding"):
        return HTMLResponse(open(ONBOARDING).read())
    if path.startswith("app"):
        return HTMLResponse(open(UI).read())
    return HTMLResponse(open(LANDING).read())


async def _json(request: Request) -> dict:
    try:
        raw = await request.body()
        import json
        return json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
