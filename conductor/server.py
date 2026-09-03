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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .models import Status

UI = os.path.join(os.path.dirname(__file__), "ui", "index.html")

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
        decisions.append({
            "id": d.id, "question": d.root_question, "options": d.options,
            "unblocks": d.unblock_value,
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
            if self.path.startswith("/api/state"):
                with lock:
                    self._send(200, json.dumps(state(conductor)))
            elif self.path in ("/", "/index.html"):
                with open(UI, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            with lock:
                if self.path.startswith("/api/answer"):
                    conductor.answer(payload["decision_id"], payload["choice"])
                    conductor.run(ticks=4)
                elif self.path.startswith("/api/tick"):
                    conductor.run(ticks=int(payload.get("ticks", 1)))
                else:
                    return self._send(404, json.dumps({"error": "not found"}))
                self._send(200, json.dumps(state(conductor)))

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"decision surface: {url}")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    srv.serve_forever()
