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
        # The token proves identity; workspace membership decides the role. The
        # first authenticated user of an empty workspace owns it; anyone not a
        # member is authenticated but has no access here.
        from .membership import memberships
        role = memberships.ensure_owner(p.tenant, p.subject, p.email)
        if role is None:
            raise HTTPException(status_code=403, detail="not a member of this workspace")
        return Principal(subject=p.subject, tenant=p.tenant, email=p.email, roles=(role,))
    # Demo mode: each visitor gets an isolated board keyed by a cookie, so one
    # visitor cannot reset or drive another's, and two judges never collide on
    # one shared board.
    tenant = request.cookies.get("conductor_demo") or ""
    if not (tenant.startswith("demo_") and len(tenant) <= 40 and tenant[5:].isalnum()):
        tenant = "demo_" + secrets.token_hex(8)
        request.state.set_demo_tenant = tenant
    # Admin in the demo, so RBAC-gated routes are not blocked for a demo visitor.
    return Principal(subject="demo", tenant=tenant, roles=("admin", "member", "approver"))


def client_key(request: Request, p: Principal) -> str:
    """A rate-limit key: the visitor's tenant, falling back to peer IP."""
    return p.tenant if p.tenant != "default" else (request.client.host if request.client else "anon")


def require(*roles: str):
    """A dependency that authorizes by role. `require("admin")` gates a route to
    admins (and admin is a superset of every role). In demo mode the principal
    is admin, so the demo is unaffected."""
    def dep(p: Principal = Depends(caller)) -> Principal:
        if not p.has_role(*roles):
            raise HTTPException(status_code=403,
                                detail=f"requires role: {' or '.join(roles)}")
        return p
    return dep


# --- API -------------------------------------------------------------------
@app.get("/api/health")
def health():
    # NB: never expose the tenant list here. In demo mode the tenant id is the
    # visitor's session key, so enumerating tenants would let anyone hijack
    # another visitor's board by setting the cookie. Report a count only.
    from .auth import oidc_configured
    mode = "disabled"
    if auth_required():
        mode = "sso" if oidc_configured() else "session"
    return {"status": "ok", "provider": CONFIG.provider, "auth": mode,
            "active_boards": registry.count()}


@app.get("/api/whoami")
def api_whoami(p: Principal = Depends(caller)):
    """Who the caller is, for the SPA to render the signed-in user and gate UI
    by role. In demo mode this is the admin demo principal."""
    return {"subject": p.subject, "tenant": p.tenant, "email": p.email,
            "roles": list(p.roles)}


@app.get("/api/auth/config")
def api_auth_config():
    """What the SPA needs to sign a user in: the mode, and where to send them.
    login_url is the identity provider's hosted sign-in URL (operator-provided)."""
    from .auth import oidc_configured
    import os as _os
    mode = "disabled"
    if auth_required():
        mode = "sso" if oidc_configured() else "session"
    return {"mode": mode, "login_url": _os.environ.get("CONDUCTOR_OIDC_LOGIN_URL")}


def _members_payload(tenant: str) -> dict:
    from .membership import memberships
    return {"members": [{"subject": m.subject, "role": m.role, "email": m.email,
                         "added_by": m.added_by} for m in memberships.members(tenant)]}


@app.get("/api/members")
def api_members(p: Principal = Depends(caller)):
    """Everyone in this workspace and their role."""
    return _members_payload(p.tenant)


@app.post("/api/members")
async def api_member_add(request: Request, p: Principal = Depends(require("admin"))):
    """Invite/add a member. Admin only. The subject is the user's identity from
    the identity provider (its `sub`); email is for display."""
    from .membership import ROLES, memberships
    body = await _json(request)
    subject = (body.get("subject") or "").strip()
    role = (body.get("role") or "member").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="subject required")
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")
    memberships.add(p.tenant, subject, role, (body.get("email") or "").strip() or None, by=p.subject)
    return _members_payload(p.tenant)


@app.delete("/api/members/{subject}")
def api_member_remove(subject: str, p: Principal = Depends(require("admin"))):
    from .membership import memberships
    if subject == p.subject:
        raise HTTPException(status_code=400, detail="you cannot remove yourself")
    memberships.remove(p.tenant, subject)
    return _members_payload(p.tenant)


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
async def api_repo_connect(request: Request, p: Principal = Depends(require("admin"))):
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


# --- connect a GitHub repo (gated; verified work opens a draft PR) ----------
_gh_lock = __import__("threading").RLock()
_gh: dict = {"c": None, "repo": None, "dir": None}


def _gh_ready():
    """GitHub is available only when real execution is enabled AND a token is
    configured. It runs task checks as real commands, so it stays behind the
    same gate as local real-repo execution."""
    from .github import client_from_env
    from .userrepo import repo_enabled
    return repo_enabled(), client_from_env()


def _gh_payload():
    from .server import real_state
    enabled, client = _gh_ready()
    # repo_name (the owner/name identifier) is distinct from real_state's "repo"
    # (the file/branch snapshot), which is merged in below.
    out = {"enabled": enabled, "configured": client is not None,
           "repo_name": client.repo if client else None, "connected": _gh["c"] is not None}
    if _gh["c"] is not None:
        out.update(real_state(_gh["c"]))
        out["prs"] = list(getattr(_gh["c"].executor, "prs", []))
    return out


@app.get("/api/github")
def api_github_status(p: Principal = Depends(caller)):
    with _gh_lock:
        return _gh_payload()


@app.post("/api/github/connect")
async def api_github_connect(p: Principal = Depends(require("admin"))):
    import shutil as _sh
    import tempfile as _tf
    from .github import build_for_github
    enabled, client = _gh_ready()
    if not enabled:
        raise HTTPException(status_code=403, detail=(
            "GitHub execution is disabled. It runs task checks as real commands, "
            "so enable it deliberately with CONDUCTOR_ALLOW_REPO=1."))
    if client is None:
        raise HTTPException(status_code=400, detail=(
            "set CONDUCTOR_GITHUB_TOKEN and CONDUCTOR_GITHUB_REPO (owner/name) first."))

    def work():
        with _gh_lock:
            if _gh["dir"]:
                _sh.rmtree(_gh["dir"], ignore_errors=True)
            _gh["dir"] = _tf.mkdtemp(prefix="conductor-gh-")
            _gh["c"] = build_for_github(client, _gh["dir"])
            _gh["repo"] = client.repo
            return _gh_payload()
    return await run_in_threadpool(work)


@app.post("/api/github/task")
async def api_github_task(request: Request, p: Principal = Depends(caller)):
    from .userrepo import add_task
    body = await _json(request)
    if _gh["c"] is None:
        raise HTTPException(status_code=400, detail="connect the GitHub repo first")
    for f in ("title", "file", "check"):
        if not (body.get(f) or "").strip():
            raise HTTPException(status_code=400, detail=f"{f} is required")
    with _gh_lock:
        add_task(_gh["c"], body["title"], body["file"], body["check"],
                 body.get("work_kind", "code"))
        return _gh_payload()


@app.post("/api/github/run")
async def api_github_run(request: Request, p: Principal = Depends(caller)):
    body = await _json(request)
    if _gh["c"] is None:
        raise HTTPException(status_code=400, detail="connect the GitHub repo first")
    ticks = max(1, min(12, int(body.get("ticks", 6))))

    def work():
        with _gh_lock:
            _gh["c"].run(ticks=ticks)        # clone I/O, live agent, push, PR: off the loop
            return _gh_payload()
    return await run_in_threadpool(work)


@app.post("/api/github/webhook")
async def api_github_webhook(request: Request):
    """Receive GitHub events. There is deliberately no session dependency here:
    GitHub cannot send the demo cookie, so the HMAC signature IS the auth. An
    unsigned or mis-signed request is dropped."""
    import os as _os
    from .webhook import handle_event, verify_signature
    secret = _os.environ.get("CONDUCTOR_GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="webhooks not configured")
    body = await request.body()
    sig = request.headers.get("x-hub-signature-256")
    if not verify_signature(secret, body, sig):
        raise HTTPException(status_code=401, detail="invalid signature")
    import json as _json_mod
    try:
        payload = _json_mod.loads(body or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    event = request.headers.get("x-github-event", "")
    with _gh_lock:
        return handle_event(event, payload, _gh["c"])


# --- Slack delivery --------------------------------------------------------
def _slack_client():
    import os as _os
    from .slack import SlackClient
    tok = _os.environ.get("CONDUCTOR_SLACK_BOT_TOKEN")
    return SlackClient(token=tok) if tok else None


@app.post("/api/slack/interactive")
async def api_slack_interactive(request: Request):
    """Receive a Slack button click and answer the decision. Session-less: Slack
    cannot send the cookie, so the Slack signature is the auth. A Slack workspace
    maps to one Conductor tenant (CONDUCTOR_SLACK_TENANT)."""
    import json as _json
    import os as _os
    import urllib.parse as _up
    from .slack import parse_action, verify_signature
    secret = _os.environ.get("CONDUCTOR_SLACK_SIGNING_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="slack not configured")
    body = await request.body()
    ts = request.headers.get("x-slack-request-timestamp", "")
    sig = request.headers.get("x-slack-signature")
    if not verify_signature(secret, ts, body, sig):
        raise HTTPException(status_code=401, detail="invalid slack signature")
    form = _up.parse_qs(body.decode(errors="replace"))
    try:
        payload = _json.loads(form.get("payload", ["{}"])[0])
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")
    action = parse_action(payload)
    if action is None:
        return {"text": "No answerable action."}
    did, choice = action
    tenant = _os.environ.get("CONDUCTOR_SLACK_TENANT", "default")

    def do(c):
        c.answer(did, choice)
        c.run(ticks=4)
        return True
    try:
        await run_in_threadpool(lambda: registry.write(tenant, do))
    except KeyError:
        return {"text": f"Decision {did} is no longer open."}
    return {"text": f"Answered: {choice}. The winning branch is already verified."}


@app.post("/api/slack/deliver")
async def api_slack_deliver(p: Principal = Depends(require("admin"))):
    """Post the Slack tenant's open decisions to the channel. A Slack workspace
    maps to one tenant (CONDUCTOR_SLACK_TENANT), the same one the interactive
    endpoint answers, so a posted decision is the one a button click resolves. If
    that board has no open decision yet, advance it so there is one to show."""
    import os as _os
    client = _slack_client()
    channel = _os.environ.get("CONDUCTOR_SLACK_CHANNEL")
    if client is None or not channel:
        raise HTTPException(status_code=503,
                            detail="set CONDUCTOR_SLACK_BOT_TOKEN and CONDUCTOR_SLACK_CHANNEL")
    tenant = _os.environ.get("CONDUCTOR_SLACK_TENANT", "default")

    def ensure(c):
        s = state(c)
        if not s.get("decisions"):
            c.run(ticks=8)
            s = state(c)
        return s
    s = await run_in_threadpool(lambda: registry.write(tenant, ensure))
    posted = 0
    for d in s.get("decisions", []):
        await run_in_threadpool(lambda d=d: client.post_decision(channel, d))
        posted += 1
    return {"delivered": posted, "tenant": tenant}


# --- email delivery (your SMTP/IMAP) --------------------------------------
@app.post("/api/email/deliver")
async def api_email_deliver(p: Principal = Depends(require("admin"))):
    """Email this tenant's open decisions to CONDUCTOR_EMAIL_TO over your SMTP."""
    import os as _os
    from .mailer import decision_email, mailer_from_env
    mailer = mailer_from_env()
    to = _os.environ.get("CONDUCTOR_EMAIL_TO")
    if mailer is None or not to:
        raise HTTPException(status_code=503, detail="set CONDUCTOR_SMTP_* and CONDUCTOR_EMAIL_TO")
    tenant = _os.environ.get("CONDUCTOR_EMAIL_TENANT", "default")

    def ensure(c):
        st = state(c)
        if not st.get("decisions"):
            c.run(ticks=8)
            st = state(c)
        return st
    s = await run_in_threadpool(lambda: registry.write(tenant, ensure))
    sent = 0
    for d in s.get("decisions", []):
        subject, body = decision_email(d)
        await run_in_threadpool(lambda subject=subject, body=body: mailer.send(to, subject, body))
        sent += 1
    return {"emailed": sent}


@app.post("/api/email/poll")
async def api_email_poll(p: Principal = Depends(require("admin"))):
    """Read unseen email replies over IMAP and answer the decisions they name."""
    from .mailer import reader_from_env, resolve_choice
    reader = reader_from_env()
    if reader is None:
        raise HTTPException(status_code=503, detail="set CONDUCTOR_IMAP_*")
    import os as _os
    tenant = _os.environ.get("CONDUCTOR_EMAIL_TENANT", "default")
    replies = await run_in_threadpool(reader.poll)
    s = registry.read(tenant, state)
    options = {d["id"]: d.get("options", []) for d in s.get("decisions", [])}
    answered = []
    for did, text in replies:
        choice = resolve_choice(text, options.get(did, []))
        if not choice:
            continue

        def do(c, did=did, choice=choice):
            c.answer(did, choice)
            c.run(ticks=4)
            return True
        try:
            await run_in_threadpool(lambda do=do: registry.write(tenant, do))
            answered.append({"decision": did, "choice": choice})
        except KeyError:
            pass
    return {"answered": answered}


@app.post("/api/reset")
def api_reset(p: Principal = Depends(require("admin"))):
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
