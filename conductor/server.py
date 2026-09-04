"""The decision surface.

Everything else in Conductor is machinery. This is the only part a person
looks at, so it is built around one claim: on a good day it is empty.

It reads live state, and it can equally be pointed at a replayed event log,
which is how a demo shows a real run without dispatching live agents at it.
"""

from __future__ import annotations

import json
import os
import threading
import logging

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import CONFIG

from .models import Status

log = logging.getLogger("conductor.server")

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
UI = os.path.join(UI_DIR, "index.html")
LANDING = os.path.join(UI_DIR, "landing.html")
ONBOARDING = os.path.join(UI_DIR, "onboarding.html")

_ORDER = [Status.ESCALATED, Status.REJECTED, Status.HELD, Status.DISPATCHED,
          Status.CLAIMED_DONE, Status.PENDING, Status.DONE, Status.BLOCKED]


def state(c) -> dict:
    g = c.graph
    board = []
    for cm in sorted(g, key=lambda x: (_ORDER.index(x.status) if x.status in _ORDER else 9,
                                       -g.score_risk(x))):
        board.append({
            "id": cm.id, "title": cm.title, "status": cm.status.value,
            "owner": cm.owner, "reviewer": cm.reviewer,
            "risk": g.score_risk(cm), "attempts": cm.attempts,
            "speculative": bool(cm.speculative_for),
            "branch": cm.branch, "work_kind": cm.work_kind,
            "review_cost": cm.review_cost_minutes,
            "evidence": {"kind": cm.evidence.kind.value, "spec": cm.evidence.spec,
                         "passed": cm.evidence.passed,
                         "detail": (cm.evidence.detail or "")[:200]},
            "reason": (cm.history[-1].split("  ", 1)[-1] if cm.history else ""),
        })

    decisions = []
    for d in c.surface.queue():
        spec = [b for b in c.speculation.branches.values() if b.decision_id == d.id]
        ready = sum(1 for b in spec if not b.discarded
                    for cid in b.commitments
                    if g.get(cid).status is Status.DONE)
        # The review minutes this decision is holding hostage: sum the review
        # cost of every commitment it blocks. Attention is the budget, so the
        # honest framing of a question's weight is the attention it frees.
        review_minutes = sum(g.get(cid).review_cost_minutes for cid in d.blocked
                             if g.get(cid) is not None)
        from .routing import decision_domain
        domain = decision_domain(g, d)
        led = getattr(c, "expertise", None)
        routed_to = led.best_for(domain) if led is not None else None
        decisions.append({
            "id": d.id, "question": d.root_question, "options": d.options,
            "unblocks": d.unblock_value,
            "commitments": len(d.blocked),
            "review_minutes": review_minutes,
            "domain": domain, "routed_to": routed_to,
            "compressed_from": len(d.merged_from) + 1,
            "branches": len(spec), "prebuilt": ready,
            "spent": round(c.cost.for_decision(d.id), 4),
            # A question we could not frame is one a person must frame. Saying
            # so beats rendering a decision with no way to act on it.
            "needs_framing": len(d.options) < 2,
        })

    cost = c.cost.by_outcome()
    return {
        "board": board,
        "decisions": decisions,
        "attention": [{"reviewer": b.reviewer_id, "spent": b.spent,
                       "committed": b.committed, "remaining": b.remaining,
                       "total": b.minutes_per_day}
                      for b in c.dispatcher.budgets.values()],
        "trust": [{"worker": r.id, "type": r.type.value,
                   "probation": getattr(r, "probation", False),
                   "principal": r.principal,
                   "detail": c.trust.summary_line(r.id)}
                  for r in g.resources.values()],
        "cost": {"total": round(c.cost.total, 4),
                 "verified": round(cost.get("verified", 0), 4),
                 "rejected": round(cost.get("rejected", 0), 4),
                 "discarded": round(cost.get("discarded", 0), 4),
                 "per_verified": round(c.cost.cost_per_verified(), 4),
                 "by_model": {k: round(v, 4) for k, v in c.cost.by_model().items()}},
        "metrics": vars(c.metrics),
        "events": [e[11:] for e in c.events[-40:]][::-1],
        "compression": c.surface.compression_ratio,
        "in_flight": sum(1 for x in g if x.status.value in ("dispatched", "claimed_done")),
    }


def repo_snapshot(c) -> dict:
    """The real git artifacts behind a real-execution run: the base branch's
    merge log, and the source files that actually live on the base. Only
    verified work is here, because only a passing branch was ever merged."""
    ex = getattr(c, "executor", None)
    repo = getattr(ex, "repo", None)
    log_lines = []
    files = {}
    if ex is not None:
        try:
            log_lines = ex.base_log(20)
        except Exception:  # noqa: BLE001
            log_lines = []
    if repo and os.path.isdir(repo):
        for name in sorted(os.listdir(repo)):
            if name.endswith(".py") and os.path.isfile(os.path.join(repo, name)):
                try:
                    with open(os.path.join(repo, name)) as f:
                        files[name] = f.read()[:2000]
                except OSError:
                    pass
    return {"base": getattr(ex, "base", "main"), "log": log_lines, "files": files,
            "path": os.path.basename(repo) if repo else None}


def real_state(c) -> dict:
    """state(), plus the real repository snapshot, for the real-execution view."""
    s = state(c)
    s["repo"] = repo_snapshot(c)
    return s


def activity(c, limit: int = 120) -> dict:
    """The agent activity stream: every meaningful action, attributed to the
    worker that took it, read from the durable event log. This is Conductor's
    observability, the transparent record of what each agent did and what the
    verification runner decided about it."""
    from .events import EventKind
    g = c.graph
    verbs = {
        EventKind.PLANNED: ("planned", "plan"),
        EventKind.HIRED: ("joined the roster", "hire"),
        EventKind.DISPATCHED: ("picked up", "run"),
        EventKind.CLAIMED: ("reported complete", "claim"),
        EventKind.VERIFIED: ("verified and merged", "pass"),
        EventKind.REJECTED: ("caught wrong, re-dispatched", "fail"),
        EventKind.HELD: ("held for review capacity", "hold"),
        EventKind.ESCALATED: ("raised a decision", "ask"),
        EventKind.ANSWERED: ("answered by a human", "answer"),
        EventKind.SPECULATED: ("forked speculative branches", "spec"),
        EventKind.DISCARDED: ("discarded a losing branch", "discard"),
        EventKind.BLOCKED: ("blocked by policy", "block"),
    }
    rows = []
    last_key = None
    for e in c.recorder.history():
        # A held commitment is re-recorded every tick; collapse the repeats so
        # the stream reads as actions, not polling.
        key = (e.kind, e.commitment_id)
        if e.kind is EventKind.HELD and key == last_key:
            continue
        last_key = key
        verb, tone = verbs.get(e.kind, (e.kind.value, "run"))
        title = None
        if e.commitment_id and e.commitment_id in g.commitments:
            title = g.get(e.commitment_id).title
        detail = ""
        d = e.data or {}
        if e.kind is EventKind.VERIFIED:
            detail = str(d.get("detail", ""))[:140]
        elif e.kind is EventKind.REJECTED:
            detail = str(d.get("detail", ""))[:140]
        elif e.kind is EventKind.HELD:
            detail = f"reviewer {d.get('reviewer','')} · needs {d.get('cost','?')}m"
        elif e.kind is EventKind.DISPATCHED:
            detail = f"attempt {d.get('attempt', 1)}"
        elif e.kind is EventKind.ANSWERED:
            detail = f"chose {d.get('choice','')}"
        elif e.kind is EventKind.ESCALATED:
            detail = str(d.get("question", ""))[:120]
        rows.append({
            "seq": e.seq, "at": e.at[11:19] if len(e.at) > 19 else e.at,
            "kind": e.kind.value, "tone": tone, "verb": verb,
            "actor": e.actor, "title": title, "detail": detail,
        })
    rows = rows[-limit:][::-1]
    # a compact by-worker tally for the header
    by_worker: dict[str, dict] = {}
    from .events import EventKind as EK
    for e in c.recorder.history():
        if e.actor and e.kind in (EK.VERIFIED, EK.REJECTED):
            w = by_worker.setdefault(e.actor, {"verified": 0, "caught": 0})
            w["verified" if e.kind is EK.VERIFIED else "caught"] += 1
    return {"events": rows, "by_worker": by_worker}


def team(c) -> dict:
    """The roster: humans and agents as one team, plus any hiring the graph
    currently justifies. An agent is a colleague with a record, not a
    configured integration."""
    from .roster import Roster
    g = c.graph
    roster = Roster(graph=g, trust=c.trust)

    members = []
    for r in g.resources.values():
        agent = r.type.value == "agent"
        skills = []
        for k in (r.skills or ["general"]):
            rec = c.trust.records.get((r.id, k))
            if rec:
                skills.append({"kind": k, "score": round(rec.score, 2),
                               "passes": rec.passes, "total": rec.passes + rec.failures})
            else:
                skills.append({"kind": k, "score": None, "passes": 0, "total": 0})
        purpose = {
            "human_sam": "Product judgment and review",
            "human_sarah": "Design",
            "agent_impl": "Writes and fixes application code",
            "agent_research": "Competitive and technical research",
            "agent_delegate": "Handles Sam's review prep: diffs, drafts, follow-ups",
        }.get(r.id, "General work")
        budget = c.dispatcher.budgets.get(r.id)
        members.append({
            "id": r.id, "name": r.name, "type": r.type.value,
            "purpose": purpose, "skills": skills,
            "probation": getattr(r, "probation", False) if agent else False,
            "principal": r.principal, "scopes": r.scopes,
            "budget": budget.minutes_per_day if budget else None,
        })
    # Humans first, then agents; delegates sit under their principal.
    members.sort(key=lambda m: (m["type"] == "agent", m["principal"] or "", m["id"]))

    proposals = []
    for kind, n in roster.bottlenecks(min_waiting=1):
        p = roster.propose_hire(kind, n)
        proposals.append({"kind": kind, "queued": n, "question": p["question"],
                          "options": p["options"]})

    return {"members": members, "proposals": proposals}


def decision_detail(c, decision_id: str) -> dict:
    """Everything behind one question: the branches built while it waited, the
    work verified inside each, and the escalations it was compressed from.

    This is the view that shows what no other tool can, that the waiting time
    was already spent doing the work."""
    g = c.graph
    d = c.surface.open.get(decision_id)
    if d is None:
        for a in c.surface.answered:
            if a.id == decision_id:
                d = a
                break
    if d is None:
        return {"error": "unknown decision"}

    branches = []
    for b in sorted((b for b in c.speculation.branches.values()
                     if b.decision_id == d.id), key=lambda b: b.option):
        work = []
        for cid in b.commitments:
            cm = g.get(cid)
            work.append({"title": cm.title, "status": cm.status.value,
                         "evidence": cm.evidence.spec,
                         "passed": cm.evidence.passed})
        verified = sum(1 for w in work if w["status"] == "done")
        branches.append({
            "option": b.option, "cost": round(c.cost.for_branch(b.id), 4),
            "verified": verified, "total": len(work),
            "chosen": d.answer == b.option,
            "discarded": b.discarded, "work": work})

    return {
        "id": d.id, "question": d.root_question, "options": d.options,
        "answer": d.answer, "unblocks": d.unblock_value,
        "compressed_from": [{"id": cid, "title": g.get(cid).title
                             if cid in g.commitments else cid}
                            for cid in ([*d.merged_from, *d.blocked])],
        "branches": branches,
        "spent": round(c.cost.for_decision(d.id), 4),
        "needs_framing": len(d.options) < 2,
    }


def serve(conductor, port: int = 7616, open_browser: bool = True):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            try:
                self._route_get()
            except BrokenPipeError:
                pass
            except Exception as e:  # noqa: BLE001
                log.exception("GET %s failed", self.path)
                self._send(500, json.dumps({"error": "internal error",
                                            "detail": str(e)[:200]}))

        def _route_get(self):
            if self.path.startswith("/api/health"):
                self._send(200, json.dumps({"status": "ok",
                    "provider": CONFIG.provider,
                    "commitments": len(conductor.graph.commitments),
                    "open_decisions": len(conductor.surface.open)}))
            elif self.path.startswith("/api/team"):
                with lock:
                    self._send(200, json.dumps(team(conductor)))
            elif self.path.startswith("/api/activity"):
                with lock:
                    self._send(200, json.dumps(activity(conductor)))
            elif self.path.startswith("/api/plan"):
                from .planning import propose
                with lock:
                    self._send(200, json.dumps(propose()))
            elif self.path.startswith("/api/decision"):
                from urllib.parse import parse_qs, urlparse
                did = parse_qs(urlparse(self.path).query).get("id", [""])[0]
                with lock:
                    self._send(200, json.dumps(decision_detail(conductor, did)))
            elif self.path.startswith("/api/state"):
                with lock:
                    self._send(200, json.dumps(state(conductor)))
            elif self.path.startswith("/shot/"):
                name = os.path.basename(self.path.split("?")[0])
                path = os.path.join(os.path.dirname(UI_DIR), "..", "docs", "shots", name)
                if os.path.isfile(path):
                    with open(path, "rb") as f:
                        self._send(200, f.read(), "image/png")
                else:
                    self._send(404, json.dumps({"error": "no shot"}))
            elif self.path.split("?")[0] in ("/signup", "/onboarding"):
                with open(ONBOARDING, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif self.path.split("?")[0] in ("/", "/index.html"):
                with open(LANDING, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif not self.path.startswith("/api"):
                # /app and anything else non-API serves the SPA; the client
                # reads its own query string for view/theme/deep-links.
                with open(UI, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                if n > 1_000_000:
                    return self._send(413, json.dumps({"error": "payload too large"}))
                payload = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(400, json.dumps({"error": "invalid JSON"}))
            try:
                with lock:
                    if self.path.startswith("/api/answer"):
                        if "decision_id" not in payload or "choice" not in payload:
                            return self._send(400, json.dumps(
                                {"error": "decision_id and choice required"}))
                        conductor.answer(payload["decision_id"], payload["choice"])
                        conductor.run(ticks=4)
                    elif self.path.startswith("/api/tick"):
                        conductor.run(ticks=max(1, min(20, int(payload.get("ticks", 1)))))
                    else:
                        return self._send(404, json.dumps({"error": "not found"}))
                    self._send(200, json.dumps(state(conductor)))
            except KeyError as e:
                self._send(404, json.dumps({"error": f"unknown id: {e}"}))
            except BrokenPipeError:
                pass
            except Exception as e:  # noqa: BLE001
                log.exception("POST %s failed", self.path)
                self._send(500, json.dumps({"error": "internal error",
                                            "detail": str(e)[:200]}))

    host, port = CONFIG.host, port or CONFIG.port
    srv = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    log.info("conductor serving at %s (provider=%s)", url, CONFIG.provider)
    print(f"conductor: {url}")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
