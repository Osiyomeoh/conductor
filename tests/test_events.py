"""Sequence allocation: store-owned, unique, and atomic on DynamoDB.

The local store must hand out unique sequence numbers under concurrent threads,
and the DynamoDB store must allocate them with a single atomic UpdateItem ADD, so
more than one instance can write the same tenant without colliding.
"""
import threading

from conductor.events import DynamoStore, MemoryStore, Recorder
from conductor.models import Status  # noqa: F401  (ensures package imports)


def test_memory_next_seq_is_unique_under_threads():
    store = MemoryStore()
    seen = []
    lock = threading.Lock()

    def worker():
        for _ in range(50):
            n = store.next_seq("t")
            with lock:
                seen.append(n)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(seen) == 400
    assert len(set(seen)) == 400            # every number handed out once
    assert sorted(seen) == list(range(1, 401))


def test_recorder_uses_store_next_seq():
    r = Recorder(MemoryStore(), tenant="t")
    from conductor.events import EventKind
    e1 = r.record(EventKind.DISPATCHED, actor="a")
    e2 = r.record(EventKind.VERIFIED, actor="a")
    assert (e1.seq, e2.seq) == (1, 2)


class FakeTable:
    def __init__(self):
        self.counter = {}
        self.updates = []

    def update_item(self, **kw):
        self.updates.append(kw)
        tenant = kw["Key"]["tenant"]
        assert kw["Key"]["seq"] == 0                       # the counter row
        assert kw["UpdateExpression"] == "ADD nextseq :one"
        self.counter[tenant] = self.counter.get(tenant, 0) + 1
        return {"Attributes": {"nextseq": self.counter[tenant]}}


def test_dynamo_next_seq_is_a_single_atomic_add():
    store = DynamoStore.__new__(DynamoStore)      # bypass boto client in __init__
    store.table = FakeTable()
    assert store.next_seq("acme") == 1
    assert store.next_seq("acme") == 2
    assert store.next_seq("beta") == 1            # per-tenant counter
    assert len(store.table.updates) == 3          # one UpdateItem per allocation
