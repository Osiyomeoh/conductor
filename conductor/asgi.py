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
from starlette.concurrency import run_in_threadpool

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


def _store_for(tenant: str):
    """Anonymous demo visitors get an ephemeral in-memory board by design: they
    are throwaway sessions, so persisting each one to DynamoDB would only cost
    money and leave garbage rows. Real (authenticated) tenants get the durable
    store configured for the deployment, so their state survives restarts."""
    if tenant.startswith("demo_"):
        from .events import MemoryStore
        return MemoryStore()
    return CONFIG.store()


registry = Registry(build_fn=lambda _store, tenant: persistent(store=_store_for(tenant), tenant=tenant))


import secrets

# In-process rate limiter for the expensive endpoints. The public demo has auth
# disabled, so without this a single visitor could loop the planner and drain
# the model quota, or hammer the git-worktree runner. Fixed window per key.
_rate: dict[str, list] = {}


def rate_limit(key: str, limit: int, window: float = 60.0):
    now = time.time()
    if len(_rate) > 4000:                      # bound memory under abuse
        cutoff = now - window
        for k in [k for k, v in _rate.items() if v[0] < cutoff]:
            _rate.pop(k, None)
    bucket = _rate.get(key)
    if bucket is None or now - bucket[0] > window:
        _rate[key] = [now, 1]
        return
    if bucket[1] >= limit:
        raise HTTPException(status_code=429,
                            detail="too many requests; slow down and try again shortly")
    bucket[1] += 1


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
    # Persist a per-visitor demo tenant so each browser gets its own board.
    token = getattr(request.state, "set_demo_tenant", None)
    if token:
        response.set_cookie("conductor_demo", token, httponly=True, samesite="lax",
                            secure=request.url.scheme == "https", max_age=604800)
    return response


def caller(request: Request) -> Principal:
    if auth_required():
        p = principal_from(request.headers, request.cookies)
        if p is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return p
    # Demo mode: each visitor gets an isolated board keyed by a cookie, so one
    # visitor cannot reset or drive another's, and two judges never collide on
    # one shared board.
    tenant = request.cookies.get("conductor_demo") or ""
    if not (tenant.startswith("demo_") and len(tenant) <= 40 and tenant[5:].isalnum()):
        tenant = "demo_" + secrets.token_hex(8)
        request.state.set_demo_tenant = tenant
    return Principal(subject="demo", tenant=tenant)


def client_key(request: Request, p: Principal) -> str:
    """A rate-limit key: the visitor's tenant, falling back to peer IP."""
    return p.tenant if p.tenant != "default" else (request.client.host if request.client else "anon")


# --- API -------------------------------------------------------------------
@app.get("/api/health")
def health():
    # NB: never expose the tenant list here. In demo mode the tenant id is the
    # visitor's session key, so enumerating tenants would let anyone hijack
    # another visitor's board by setting the cookie. Report a count only.
    return {"status": "ok", "provider": CONFIG.provider,
            "auth": "enforced" if auth_required() else "disabled",
            "active_boards": registry.count()}


@app.get("/api/state")
def api_state(p: Principal = Depends(caller)):
    return registry.read(p.tenant, state)


@app.get("/api/team")
def api_team(p: Principal = Depends(caller)):
    return registry.read(p.tenant, team)


@app.get("/api/activity")
def api_activity(p: Principal = Depends(caller)):
    return registry.read(p.tenant, activity)


@app.get("/api/decision")
def api_decision(id: str, p: Principal = Depends(caller)):
    detail = registry.read(p.tenant, lambda c: decision_detail(c, id))
    if isinstance(detail, dict) and detail.get("error"):
        raise HTTPException(status_code=404, detail="unknown decision")
    return detail


# --- real execution -------------------------------------------------------
# A single real-repo conductor, built lazily against an isolated temp repo. It
# runs the fixed coding backlog (not arbitrary caller input, which on a public
# endpoint would be remote code execution) in real git worktrees, verified by
# real commands, merged only when the check passes.
import shutil
import tempfile

_real_lock = __import__("threading").RLock()
_real: dict = {"c": None, "repo": None, "live": None}


def _real_conductor(live: bool):
    from .realworld import build as build_real
    if _real["c"] is None or _real["live"] != live:
        if _real["repo"]:
            shutil.rmtree(_real["repo"], ignore_errors=True)
        _real["repo"] = tempfile.mkdtemp(prefix="conductor-real-")
        _real["c"] = build_real(_real["repo"], live=live)
        _real["live"] = live
    return _real["c"]


@app.get("/api/real/state")
def api_real_state(p: Principal = Depends(caller)):
    from .server import real_state
    with _real_lock:
        return real_state(_real_conductor(_real["live"] or False))


@app.post("/api/real/run")
async def api_real_run(request: Request, p: Principal = Depends(caller)):
    from .planning import live_available
    from .server import real_state
    rate_limit(f"real:{client_key(request, p)}", limit=10)
    body = await _json(request)
    ticks = max(1, min(12, int(body.get("ticks", 8))))
    live = bool(body.get("live", False)) and live_available()

    def work():
        with _real_lock:
            c = _real_conductor(live)
            c.run(ticks=ticks)          # git subprocesses: must not run on the event loop
            s = real_state(c)
            s["live"] = live
            return s
    return await run_in_threadpool(work)


@app.post("/api/real/reset")
async def api_real_reset(request: Request, p: Principal = Depends(caller)):
    from .planning import live_available
    from .server import real_state
    body = await _json(request)
    live = bool(body.get("live", False)) and live_available()

    def work():
        with _real_lock:
            if _real["repo"]:
                shutil.rmtree(_real["repo"], ignore_errors=True)
            _real["c"] = None
            return real_state(_real_conductor(live))
    return await run_in_threadpool(work)


# --- connect your own repo (gated, local/authenticated) --------------------
_repo_lock = __import__("threading").RLock()
_repo: dict = {"c": None, "path": None}


def _require_repo_enabled():
    from .userrepo import repo_enabled
    if not repo_enabled():
        raise HTTPException(status_code=403, detail=(
            "real-repo execution is disabled. It runs task checks as real "
            "commands against your repository, so it is off by default. Enable it "
            "deliberately, locally, with CONDUCTOR_ALLOW_REPO=1."))


def _repo_payload():
    from .server import real_state
    out = {"enabled": True, "connected": _repo["c"] is not None,
           "path": _repo["path"]}
    if _repo["c"] is not None:
        from .planning import live_available
        out.update(real_state(_repo["c"]))
        out["live"] = live_available()
    return out


@app.get("/api/repo")
def api_repo_status(p: Principal = Depends(caller)):
    from .userrepo import repo_enabled
    if not repo_enabled():
        return {"enabled": False, "connected": False}
    with _repo_lock:
        return _repo_payload()


@app.post("/api/repo/connect")
async def api_repo_connect(request: Request, p: Principal = Depends(caller)):
    _require_repo_enabled()
    from .userrepo import build_for_repo, validate_repo
    body = await _json(request)
    ok, resolved = validate_repo(body.get("path", ""))
    if not ok:
        raise HTTPException(status_code=400, detail=resolved)

    def work():
        with _repo_lock:
            _repo["c"] = build_for_repo(resolved)   # git init/config: off the loop
            _repo["path"] = resolved
            return _repo_payload()
    return await run_in_threadpool(work)


@app.post("/api/repo/task")
async def api_repo_task(request: Request, p: Principal = Depends(caller)):
    _require_repo_enabled()
    from .userrepo import add_task
    body = await _json(request)
    if _repo["c"] is None:
        raise HTTPException(status_code=400, detail="connect a repository first")
    for f in ("title", "file", "check"):
        if not (body.get(f) or "").strip():
            raise HTTPException(status_code=400, detail=f"{f} is required")
    with _repo_lock:
        add_task(_repo["c"], body["title"], body["file"], body["check"],
                 body.get("work_kind", "code"))
        return _repo_payload()


@app.post("/api/repo/run")
async def api_repo_run(request: Request, p: Principal = Depends(caller)):
    _require_repo_enabled()
    body = await _json(request)
    if _repo["c"] is None:
        raise HTTPException(status_code=400, detail="connect a repository first")
    ticks = max(1, min(12, int(body.get("ticks", 6))))

    def work():
        with _repo_lock:
            _repo["c"].run(ticks=ticks)     # git + live agent: off the event loop
            return _repo_payload()
    return await run_in_threadpool(work)


@app.post("/api/repo/disconnect")
def api_repo_disconnect(p: Principal = Depends(caller)):
    _require_repo_enabled()
    with _repo_lock:
        _repo["c"] = None
        _repo["path"] = None
        return {"enabled": True, "connected": False}


@app.post("/api/reset")
def api_reset(p: Principal = Depends(caller)):
    """Rebuild this tenant from a fresh seed. The guided demo calls this so a
    cold visitor always starts from the same clean board."""
    return registry.reset(p.tenant, lambda c: state(c))


@app.post("/api/tick")
async def api_tick(request: Request, p: Principal = Depends(caller)):
    body = await _json(request)
    ticks = max(1, min(20, int(body.get("ticks", 1))))
    return await run_in_threadpool(
        lambda: registry.write(p.tenant, lambda c: (c.run(ticks=ticks), state(c))[1]))


@app.post("/api/plan")
async def api_plan(request: Request, p: Principal = Depends(caller)):
    """Turn a spoken sprint into a reviewable plan. Uses the live Strands
    Planner when a provider is configured, and a fixture otherwise, both through
    the same evidence gate."""
    from .planning import live_available, propose
    rate_limit(f"plan:{client_key(request, p)}", limit=12)
    body = await _json(request)
    intent = (body.get("intent") or "").strip()[:2000] or None    # cap: no unbounded prompt
    live = live_available()
    return await run_in_threadpool(lambda: propose(intent, live=live))   # model call: off the loop


@app.post("/api/approve")
async def api_approve(request: Request, p: Principal = Depends(caller)):
    """Approve a planned sprint: materialise its commitments into the tenant's
    running conductor and start the loop. This is the whole arc, from one
    conversation to a team doing the work."""
    from .planning import live_available, plan_commitments
    rate_limit(f"approve:{client_key(request, p)}", limit=12)
    body = await _json(request)
    intent = (body.get("intent") or "").strip()[:2000]
    if not intent:
        raise HTTPException(status_code=400, detail="intent required")
    live = live_available()

    def work():
        made, _rejected, source, _plan = plan_commitments(intent, live=live)

        def do(c):
            for cm in made:
                c.graph.add(cm)
            c.run(ticks=4)
            s = state(c)
            s["approved"] = len(made)
            s["planned_by"] = source
            return s
        return registry.write(p.tenant, do)
    return await run_in_threadpool(work)


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
        return await run_in_threadpool(lambda: registry.write(p.tenant, do))
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
