"""Per-tenant conductors, each independently locked.

A single global lock serialises every request across every tenant: one team's
tick blocks another team's read. In production each tenant gets its own
Conductor, its own durable log, and its own lock, so work is isolated and
concurrent. Conductors are built lazily on first access and resumed from their
durable log, so a restart brings every active tenant back.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .config import CONFIG


@dataclass
class _Entry:
    conductor: object
    lock: threading.RLock


@dataclass
class Registry:
    build_fn: object                       # (store, tenant) -> Conductor
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _guard: threading.Lock = field(default_factory=threading.Lock)

    def _entry(self, tenant: str) -> _Entry:
        # Double-checked: the global guard is held only to create an entry, not
        # to use one, so tenants never wait on each other's work.
        e = self._entries.get(tenant)
        if e is not None:
            return e
        with self._guard:
            e = self._entries.get(tenant)
            if e is None:
                c = self.build_fn(CONFIG.store(), tenant)
                e = _Entry(conductor=c, lock=threading.RLock())
                self._entries[tenant] = e
            return e

    def read(self, tenant: str, fn):
        """A read holds only this tenant's lock, briefly."""
        e = self._entry(tenant)
        with e.lock:
            return fn(e.conductor)

    def write(self, tenant: str, fn):
        """A write (tick/answer) holds only this tenant's lock."""
        e = self._entry(tenant)
        with e.lock:
            return fn(e.conductor)

    def reset(self, tenant: str, fn=None):
        """Rebuild a tenant's conductor from a fresh seed, discarding in-memory
        state. Used by the guided demo so every visitor starts from the same
        clean board. Holds the tenant's lock so no tick races the rebuild."""
        e = self._entry(tenant)
        with e.lock:
            e.conductor = self.build_fn(CONFIG.store(), tenant)
            return fn(e.conductor) if fn else None

    def tenants(self) -> list[str]:
        return list(self._entries)
