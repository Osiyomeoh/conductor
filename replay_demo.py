"""Persist a real run, then rebuild it from nothing but the log."""

import os, shutil, tempfile

from conductor.events import JsonlStore
from conductor.graph import CommitmentGraph
from conductor.models import Status
from conductor.replay import rebuild, summarise
from conductor.world import build

B, D, R, G = "\033[1m", "\033[2m", "\033[0m", "\033[32m"

tmp = tempfile.mkdtemp()
log = os.path.join(tmp, "conductor.jsonl")

# 1. A real run, persisted as it goes.
c = build(store=JsonlStore(log))
c.run(ticks=6)
q = [d for d in c.surface.queue() if len(d.options) >= 2]
if q:
    c.answer(q[0].id, q[0].options[0])
    c.run(ticks=6)

original = {x.id: x.status for x in c.graph}
print(f"{B}Live run{R}")
print(f"  {len(original)} commitments, {sum(1 for s in original.values() if s is Status.DONE)} verified done")
print(f"  log: {os.path.getsize(log)} bytes, {sum(1 for _ in open(log))} events")

# 2. Rebuild from the log alone. No workers, no verification, no model, no spend.
fresh = CommitmentGraph()
seq = rebuild(fresh, JsonlStore(log).read())
rebuilt = {x.id: x.status for x in fresh}

print(f"\n{B}Rebuilt from the log{R}  {D}no workers ran, no checks executed, nothing spent{R}")
print(f"  reached sequence {seq}")
print(f"  {len(rebuilt)} commitments reconstructed")

drift = {k: (original[k], rebuilt.get(k)) for k in original if original[k] is not rebuilt.get(k)}
if drift:
    print(f"\n  DRIFT in {len(drift)}:")
    for k, (a, b) in list(drift.items())[:6]:
        print(f"    {k}  live={a.value}  replay={b.value if b else 'missing'}")
else:
    print(f"  {G}identical to the live run{R}")

print(f"\n{B}What the log says happened{R}")
for kind, n in sorted(summarise(JsonlStore(log).read()).items(), key=lambda x: -x[1]):
    print(f"  {kind:<12} {n}")

shutil.rmtree(tmp)
