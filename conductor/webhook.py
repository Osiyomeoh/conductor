"""GitHub webhook receiver: close the loop when a human acts on a draft PR.

Conductor opens a draft PR and stops; the human reviews and merges. This is how
Conductor hears back. GitHub POSTs an event, signed with the App's webhook
secret, and we:

  - verify the signature first (an unsigned or mis-signed request is dropped,
    because the endpoint cannot be behind the session cookie GitHub does not
    send);
  - correlate the PR to the commitment that opened it (branch = conductor/<id>);
  - record the human's action as a real event: approved, changes requested, or
    merged.

Nothing here can mark work done that was not verified. It only records what a
human decided about already-verified work.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """True only when X-Hub-Signature-256 matches an HMAC-SHA256 of the raw body
    under the shared secret. Constant-time; a missing secret or header fails."""
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _pr_record(conductor, number: int):
    ex = getattr(conductor, "executor", None)
    for p in getattr(ex, "prs", []) or []:
        if p.get("number") == number:
            return p
    return None


def _resolve_ci(conductor, branch: str, ok: bool):
    """Let the repo's CI be the verdict: find the commitment on this branch whose
    evidence is CI and still pending, and resolve it. This is the only place a CI
    result becomes 'done' — the worker's claim never was believed."""
    from .models import EvidenceKind, Status
    g = getattr(conductor, "graph", None)
    if g is None or not branch:
        return None
    for cm in g:
        if (cm.branch == branch and cm.evidence.kind is EvidenceKind.CI
                and cm.evidence.passed is None):
            cm.evidence.passed = ok
            cm.evidence.detail = "CI passed" if ok else "CI failed"
            cm.status = Status.DONE if ok else Status.REJECTED
            cm.log(f"CI {'passed' if ok else 'failed'} on {branch}")
            conductor.emit(f"CI {'passed' if ok else 'failed'} for {cm.id} on {branch}")
            return cm.id
    return None


def handle_event(event_type: str, payload: dict, conductor) -> dict:
    """Route a verified event to an effect on the connected conductor. Returns a
    small summary of what was recorded. Unknown events are acknowledged and
    ignored, which is what GitHub expects."""
    if conductor is None:
        return {"handled": False, "reason": "no connected repo"}

    if event_type == "ping":
        return {"handled": True, "event": "ping"}

    if event_type == "check_suite":
        cs = payload.get("check_suite", {}) or {}
        if payload.get("action") == "completed":
            ok = cs.get("conclusion") == "success"
            cid = _resolve_ci(conductor, cs.get("head_branch", ""), ok)
            return {"handled": bool(cid), "event": "ci",
                    "result": "pass" if ok else "fail", "commitment": cid}
        return {"handled": True, "event": f"check_suite.{payload.get('action')}"}

    if event_type == "status":
        # Ignore our own status (context conductor/*); only the repo's real CI is
        # the CI verdict.
        if (payload.get("context") or "").startswith("conductor/"):
            return {"handled": True, "event": "status.self"}
        state = payload.get("state")
        if state in ("success", "failure"):
            for b in payload.get("branches", []) or []:
                cid = _resolve_ci(conductor, b.get("name", ""), state == "success")
                if cid:
                    return {"handled": True, "event": "ci",
                            "result": "pass" if state == "success" else "fail", "commitment": cid}
        return {"handled": True, "event": f"status.{state}"}

    if event_type == "pull_request":
        pr = payload.get("pull_request", {}) or {}
        number = pr.get("number")
        action = payload.get("action")
        rec = _pr_record(conductor, number)
        if action == "closed" and pr.get("merged"):
            if rec:
                rec["state"] = "merged"
            conductor.emit(f"human merged PR #{number}: {pr.get('title', '')}")
            return {"handled": True, "event": "merged", "pr": number}
        if action == "closed":
            if rec:
                rec["state"] = "closed"
            conductor.emit(f"human closed PR #{number} without merging")
            return {"handled": True, "event": "closed", "pr": number}
        return {"handled": True, "event": f"pull_request.{action}", "pr": number}

    if event_type == "pull_request_review":
        review = payload.get("review", {}) or {}
        number = (payload.get("pull_request", {}) or {}).get("number")
        state = (review.get("state") or "").lower()
        rec = _pr_record(conductor, number)
        if state == "approved":
            if rec:
                rec["state"] = "approved"
            conductor.emit(f"human approved PR #{number}")
            return {"handled": True, "event": "approved", "pr": number}
        if state == "changes_requested":
            if rec:
                rec["state"] = "changes_requested"
            conductor.emit(f"human requested changes on PR #{number}")
            return {"handled": True, "event": "changes_requested", "pr": number}
        return {"handled": True, "event": f"review.{state}", "pr": number}

    return {"handled": False, "event": event_type}
