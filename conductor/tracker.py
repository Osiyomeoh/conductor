"""Issue-tracker sync (Linear): commitments become issues, kept up to date.

Conductor is the brain; the tracker stays the shared record. When a sprint is
approved, each commitment can be mirrored as a Linear issue carrying its proof,
and as the work resolves Conductor comments the verdict back onto the issue, so a
team watching Linear sees the same truth without leaving it.

One-way push (Conductor -> Linear). The GraphQL transport is injectable, so the
mutations are unit-tested without a Linear workspace. Jira would be a second
client behind the same two methods.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

ENDPOINT = "https://api.linear.app/graphql"

_CREATE = ("mutation($t:String!,$d:String,$team:String!){"
           "issueCreate(input:{title:$t,description:$d,teamId:$team})"
           "{success issue{id identifier url}}}")
_COMMENT = ("mutation($i:String!,$b:String!){"
            "commentCreate(input:{issueId:$i,body:$b}){success}}")


@dataclass
class LinearClient:
    api_key: str
    team_id: str
    opener: object = None      # (method, url, headers, body) -> (status, bytes)

    def _gql(self, query: str, variables: dict) -> dict:
        body = json.dumps({"query": query, "variables": variables}).encode()
        headers = {"Authorization": self.api_key, "Content-Type": "application/json",
                   "User-Agent": "conductor"}
        if self.opener is not None:
            status, data = self.opener("POST", ENDPOINT, headers, body)
        else:
            req = urllib.request.Request(ENDPOINT, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:   # noqa: S310
                status, data = r.status, r.read()
        out = json.loads(data or b"{}")
        if out.get("errors"):
            raise RuntimeError(f"linear error: {out['errors']}")
        return out.get("data", {})

    def create_issue(self, title: str, description: str) -> dict:
        d = self._gql(_CREATE, {"t": title[:250], "d": description, "team": self.team_id})
        return d.get("issueCreate", {}).get("issue", {})

    def comment(self, issue_id: str, body: str) -> bool:
        d = self._gql(_COMMENT, {"i": issue_id, "b": body})
        return bool(d.get("commentCreate", {}).get("success"))


def sync(conductor, client: LinearClient) -> dict:
    """Push commitments to Linear once, then comment status changes. State lives
    on the conductor so a re-sync neither duplicates issues nor loses the verdict."""
    mapping = getattr(conductor, "_tracker_issues", None)
    if mapping is None:
        mapping = conductor._tracker_issues = {}
    seen_status = getattr(conductor, "_tracker_status", None)
    if seen_status is None:
        seen_status = conductor._tracker_status = {}

    created, commented = 0, 0
    for cm in conductor.graph:
        if cm.id not in mapping:
            desc = f"Proof: `{cm.evidence.spec or cm.evidence.kind.value}`\n\nMirrored from Conductor."
            issue = client.create_issue(cm.title, desc)
            if issue.get("id"):
                mapping[cm.id] = issue["id"]
                created += 1
        issue_id = mapping.get(cm.id)
        status = cm.status.value
        if issue_id and seen_status.get(cm.id) != status and status in ("done", "rejected"):
            verdict = "✅ Verified and merged." if status == "done" else "❌ Rejected: the check failed."
            client.comment(issue_id, f"Conductor: {verdict} ({cm.evidence.detail or status})")
            seen_status[cm.id] = status
            commented += 1
    return {"created": created, "commented": commented, "issues": len(mapping)}


def client_from_env() -> "LinearClient | None":
    key = os.environ.get("CONDUCTOR_LINEAR_API_KEY")
    team = os.environ.get("CONDUCTOR_LINEAR_TEAM_ID")
    return LinearClient(api_key=key, team_id=team) if key and team else None
