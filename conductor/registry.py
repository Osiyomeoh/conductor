"""Per-tenant conductors, each independently locked.

Each tenant gets its own Conductor, its own durable log, and its own lock, so
work is isolated and concurrent. Conductors are built lazily on first access and
resumed from their durable log, so a restart brings every active tenant back.

The live set is bounded (LRU): anonymous demo visitors each get a tenant, so an
unbounded map would be a memory leak under a crawler. When the cap is exceeded
the least-recently-used tenant is evicted from memory; if it is durable it
simply resumes from its log the next time it is touched, so eviction loses
nothing that was persisted.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from .config import CONFIG

MAX_TENANTS = 500


@dataclass
class _Entry:
    conductor: object
    lock: threading.RLock


@dataclass
class Registry:
    build_fn: object                       # (store, tenant) -> Conductor
    max_tenants: int = MAX_TENANTS
    _entries: "OrderedDict[str, _Entry]" = field(default_factory=OrderedDict)
    _guard: threading.Lock = field(default_factory=threading.Lock)

    def _entry(self, tenant: str) -> _Entry:
        # Double-checked: the global guard is held only to create an entry (and
        # to mark it most-recently-used), not to use one, so tenants never wait
        # on each other's work.
        e = self._entries.get(tenant)
        if e is not None:
            with self._guard:
                if tenant in self._entries:
                    self._entries.move_to_end(tenant)
            return e
        with self._guard:
            e = self._entries.get(tenant)
            if e is None:
                c = self.build_fn(CONFIG.store(), tenant)
                e = _Entry(conductor=c, lock=threading.RLock())
                self._entries[tenant] = e
                while len(self._entries) > self.max_tenants:
                    self._entries.popitem(last=False)   # evict least-recently-used
            else:
                self._entries.move_to_end(tenant)
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

    def count(self) -> int:
        """How many boards are live in memory. Safe to expose; the ids are not."""
        return len(self._entries)
