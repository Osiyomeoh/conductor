"""Workspace membership: who belongs to a workspace, and at what role.

The identity provider says who a person is; this says what they are allowed to
do here. It is the authority for role-based access, not the token's claims: a
user carries an identity everywhere but a role only within a workspace they were
added to.

Bootstrapping: the first authenticated user of an empty workspace becomes its
admin (owner), so the first person in can invite the rest. After that, only an
admin adds or removes members.

In-memory for now (per process); the interface is small enough to back with the
same event store the rest of the system uses when durable org state is needed.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

ROLES = ("admin", "approver", "member", "viewer")


@dataclass
class Member:
    subject: str
    role: str
    email: str | None = None
    added_by: str | None = None
    added_at: float = 0.0


class MembershipRegistry:
    def __init__(self):
        self._by_tenant: dict[str, dict[str, Member]] = {}
        self._lock = threading.RLock()

    def members(self, tenant: str) -> list[Member]:
        with self._lock:
            return list(self._by_tenant.get(tenant, {}).values())

    def role_of(self, tenant: str, subject: str) -> str | None:
        with self._lock:
            m = self._by_tenant.get(tenant, {}).get(subject)
            return m.role if m else None

    def add(self, tenant: str, subject: str, role: str = "member",
            email: str | None = None, by: str | None = None) -> Member:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}; one of {ROLES}")
        with self._lock:
            t = self._by_tenant.setdefault(tenant, {})
            t[subject] = Member(subject, role, email, by, time.time())
            return t[subject]

    def remove(self, tenant: str, subject: str) -> bool:
        with self._lock:
            return self._by_tenant.get(tenant, {}).pop(subject, None) is not None

    def ensure_owner(self, tenant: str, subject: str, email: str | None = None) -> str:
        """The first authenticated user of an empty workspace becomes admin.
        Returns the caller's effective role (their own, or admin if bootstrapped)."""
        with self._lock:
            t = self._by_tenant.setdefault(tenant, {})
            if not t:
                t[subject] = Member(subject, "admin", email, "bootstrap", time.time())
            m = t.get(subject)
            return m.role if m else None


memberships = MembershipRegistry()
