"""Event-sourced state.

The control loop is idempotent per tick, so the durable thing is not the graph
but the sequence of facts that produced it. Persisting events rather than rows
buys three things Conductor specifically needs:

  resumable   the loop can die mid-sprint and pick up where it stopped
  replayable  a run can be reconstructed exactly, which is how you demo a
              system that dispatches real agents without dispatching them live
  auditable   "why is this done?" has an answer with a timestamp on it, which
              matters most for the one transition the whole product turns on

Events are append-only and carry a tenant, so one log can hold many teams
without the graph ever seeing another team's work.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Iterator, Protocol


class EventKind(str, Enum):
    PLANNED = "planned"           # a commitment entered the graph
    HIRED = "hired"               # a worker joined the roster
    DISPATCHED = "dispatched"
    HELD = "held"                 # no review capacity to absorb it
    CLAIMED = "claimed"           # a worker says it is finished
    VERIFIED = "verified"         # the claim survived its evidence
    REJECTED = "rejected"         # the claim did not
    ESCALATED = "escalated"
    ANSWERED = "answered"         # a human spent attention
    SPECULATED = "speculated"
    DISCARDED = "discarded"
    SPENT = "spent"               # cost attributed
    BLOCKED = "blocked"           # policy refused


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Event:
    seq: int
    kind: EventKind
    at: str
    tenant: str = "default"
    commitment_id: str | None = None
    actor: str | None = None
    decision_id: str | None = None
    data: dict = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        d["kind"] = self.kind.value
        return json.dumps(d, separators=(",", ":"), default=str)

    @staticmethod
    def from_json(line: str) -> "Event":
        d = json.loads(line)
        d["kind"] = EventKind(d["kind"])
        return Event(**d)


class EventStore(Protocol):
    def append(self, event: Event) -> None: ...
    def read(self, tenant: str = "default", since: int = 0) -> Iterator[Event]: ...
    def last_seq(self, tenant: str = "default") -> int: ...
    def next_seq(self, tenant: str = "default") -> int: ...


class MemoryStore:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def append(self, event: Event) -> None:
        self._events.append(event)

    def read(self, tenant: str = "default", since: int = 0) -> Iterator[Event]:
        return iter([e for e in self._events if e.tenant == tenant and e.seq > since])

    def last_seq(self, tenant: str = "default") -> int:
        seqs = [e.seq for e in self._events if e.tenant == tenant]
        return max(seqs, default=0)

    def next_seq(self, tenant: str = "default") -> int:
        with self._lock:
            n = self._counters.get(tenant, self.last_seq(tenant)) + 1
            self._counters[tenant] = n
            return n


class JsonlStore:
    """One append-only file. Durable enough to resume, cheap enough to diff,
    and readable by a person at three in the morning."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: Event) -> None:
        with self._lock, open(self.path, "a") as f:
            f.write(event.to_json() + "\n")
            f.flush()
            os.fsync(f.fileno())

    def read(self, tenant: str = "default", since: int = 0) -> Iterator[Event]:
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = Event.from_json(line)
                if e.tenant == tenant and e.seq > since:
                    yield e

    def last_seq(self, tenant: str = "default") -> int:
        return max((e.seq for e in self.read(tenant)), default=0)

    def next_seq(self, tenant: str = "default") -> int:
        with self._lock:                       # jsonl is a single-process store
            return self.last_seq(tenant) + 1


class DynamoStore:
    """Partitioned by tenant, sorted by sequence. The same access pattern the
    JSONL store has, so nothing above this line changes when you swap them."""

    def __init__(self, table: str, session=None, region: str = "us-west-2"):
        import boto3
        s = session or boto3.Session(region_name=region)
        self.table = s.resource("dynamodb").Table(table)

    def append(self, event: Event) -> None:
        item = {k: v for k, v in asdict(event).items() if v not in (None, {}, "")}
        item["kind"] = event.kind.value
        item["data"] = json.dumps(event.data, default=str)
        # Conditional write: a replayed tick cannot double-record a fact.
        self.table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(seq) OR seq <> :s",
            ExpressionAttributeValues={":s": event.seq})

    def read(self, tenant: str = "default", since: int = 0) -> Iterator[Event]:
        from boto3.dynamodb.conditions import Key
        kwargs = {"KeyConditionExpression": Key("tenant").eq(tenant) & Key("seq").gt(since)}
        while True:
            r = self.table.query(**kwargs)
            for item in r.get("Items", []):
                yield Event(seq=int(item["seq"]), kind=EventKind(item["kind"]),
                            at=item["at"], tenant=item["tenant"],
                            commitment_id=item.get("commitment_id"),
                            actor=item.get("actor"),
                            decision_id=item.get("decision_id"),
                            data=json.loads(item.get("data", "{}")))
            if "LastEvaluatedKey" not in r:
                return
            kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def last_seq(self, tenant: str = "default") -> int:
        from boto3.dynamodb.conditions import Key
        # seq > 0 skips the counter row (seq 0), which is not an event.
        r = self.table.query(KeyConditionExpression=Key("tenant").eq(tenant) & Key("seq").gt(0),
                             ScanIndexForward=False, Limit=1)
        items = r.get("Items", [])
        return int(items[0]["seq"]) if items else 0

    def next_seq(self, tenant: str = "default") -> int:
        """Atomic across instances: a single UpdateItem ADD on the per-tenant
        counter row (seq 0) hands out a unique, monotonic sequence number, so two
        instances writing the same tenant never collide. This is what makes the
        service safe to run on more than one instance."""
        r = self.table.update_item(
            Key={"tenant": tenant, "seq": 0},
            UpdateExpression="ADD nextseq :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW")
        return int(r["Attributes"]["nextseq"])


class Recorder:
    """Assigns sequence numbers and writes through to the store. The loop talks
    to this and never to a store directly, so persistence is one swap."""

    def __init__(self, store: EventStore | None = None, tenant: str = "default"):
        self.store = store or MemoryStore()
        self.tenant = tenant
        self.replaying = False

    def record(self, kind: EventKind, commitment_id: str | None = None,
               actor: str | None = None, decision_id: str | None = None,
               **data) -> Event | None:
        # During replay the facts already exist; recording them again would
        # duplicate history rather than rebuild it.
        if self.replaying:
            return None
        # The store hands out the sequence number: atomic across instances for
        # DynamoDB, locked within the process for the local stores. No
        # per-process counter, so more than one instance is safe.
        seq = self.store.next_seq(self.tenant)
        e = Event(seq=seq, kind=kind, at=_now(), tenant=self.tenant,
                  commitment_id=commitment_id, actor=actor,
                  decision_id=decision_id, data=data)
        self.store.append(e)
        return e

    def history(self, since: int = 0) -> Iterable[Event]:
        return self.store.read(self.tenant, since)
