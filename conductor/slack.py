"""Slack delivery: the one decision that needs a human arrives where they are.

Conductor holds everything it can and, when a real decision surfaces, posts it to
Slack as a message with the options as buttons. A click comes back to the
interactive endpoint, is verified against Slack's signing secret, and answers the
decision. Agent chatter never goes to Slack; only the questions a person must
answer.

The HTTP layer is injectable, so message shaping and signature verification are
unit-tested without a Slack workspace.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from dataclasses import dataclass

API = "https://slack.com/api"


def verify_signature(signing_secret: str, timestamp: str, body: bytes,
                     signature: str | None) -> bool:
    """Slack signs `v0:{timestamp}:{raw body}` with HMAC-SHA256. Reject a missing
    signature, a stale timestamp (replay), or a mismatch. Constant-time."""
    if not signing_secret or not signature or not timestamp:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:      # 5 min replay window
            return False
    except ValueError:
        return False
    base = f"v0:{timestamp}:{body.decode(errors='replace')}".encode()
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def decision_blocks(d: dict) -> list:
    """Block Kit for one decision: the question, what it unblocks, and a button
    per option whose value carries the decision id and the chosen option."""
    freed = f" · frees ~{d['review_minutes']}m of review" if d.get("review_minutes") else ""
    header = (f"*{d['question']}*\nunblocks {d.get('commitments', d.get('unblocks', 0))} "
              f"commitment(s){freed}")
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": header}}]
    if d.get("options"):
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": opt[:75]},
             "value": f"{d['id']}|{opt}", "action_id": f"answer_{i}"}
            for i, opt in enumerate(d["options"])]})
    else:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "No options yet: this one needs framing first."}]})
    return blocks


def parse_action(payload: dict) -> tuple[str, str] | None:
    """From a Slack interactive payload, the (decision_id, choice) the user
    clicked, or None if it is not an answer action."""
    for a in payload.get("actions", []) or []:
        val = a.get("value", "")
        if "|" in val:
            did, choice = val.split("|", 1)
            return did, choice
    return None


@dataclass
class SlackClient:
    token: str
    opener: object = None      # (method, url, headers, body_bytes) -> (status, bytes)

    def _post(self, path: str, body: dict) -> dict:
        url = f"{API}/{path}"
        raw = json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self.token}",
                   "Content-Type": "application/json; charset=utf-8",
                   "User-Agent": "conductor"}
        if self.opener is not None:
            status, data = self.opener("POST", url, headers, raw)
        else:
            req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:   # noqa: S310
                status, data = r.status, r.read()
        out = json.loads(data or b"{}")
        if not out.get("ok", False):
            raise RuntimeError(f"slack error: {out.get('error', status)}")
        return out

    def post_decision(self, channel: str, d: dict) -> dict:
        return self._post("chat.postMessage",
                          {"channel": channel, "text": d.get("question", "A decision needs you"),
                           "blocks": decision_blocks(d)})

    def post_text(self, channel: str, text: str) -> dict:
        return self._post("chat.postMessage", {"channel": channel, "text": text})
