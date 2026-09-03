"""A LIVE run: real Strands agents (Gemini) doing real coding work.

    set -a && . ./.env && set +a
    CONDUCTOR_PROVIDER=gemini python live_demo.py

Real agents write real Python into real git worktrees. The verification runner
runs the real checks; passing work merges to the base, failing work is caught
and re-dispatched. This is the deterministic real_demo, with the language model
put back in: the workers are live Strands agents, not a fixture.
"""
import os, subprocess, sys, tempfile
from conductor.models import Status
from conductor.realworld import build

C = ["\033[0m", "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[33m"]
R, D, B, G, RED, Y = C

if os.environ.get("CONDUCTOR_PROVIDER") != "gemini":
    print("set CONDUCTOR_PROVIDER=gemini (and GEMINI_API_KEY) for the live run.")
    sys.exit(1)

repo = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.mkdtemp(), "workspace")
c = build(repo, live=True)
gx = c.executor
print(f"{B}CONDUCTOR — LIVE{R}  {D}real Gemini agents, real git repo at {gx.repo}{R}")
print(f"{D}base: {gx.base} · {gx.base_log()[0]}{R}\n")

# Serial ticks so each agent call completes before the next dispatch.
print(f"{D}dispatching real agents (this makes real model calls)...{R}\n")
c.run(ticks=14)

print(f"{B}Commitments{R}")
for cm in c.graph:
    col = {Status.DONE: G, Status.REJECTED: RED}.get(cm.status, D)
    tries = f" {D}({cm.attempts} attempts){R}" if cm.attempts > 1 else ""
    print(f"  {col}{cm.status.value:<9}{R} {cm.title}{tries}")

print(f"\n{B}What reached the real base branch{R}  {D}(only verified agent work){R}")
for line in gx.base_log(10):
    print(f"  {G if 'merge' in line else D}{line}{R}")

m = c.metrics
print(f"\n{B}Summary{R}")
print(f"  {G}verified and merged   {m.verified}{R}")
print(f"  {RED}claims caught wrong   {m.claims_rejected}{R}  {D}before a human saw them{R}")
print(f"  cost                  ${c.cost.total:.4f}")
print(f"\n{D}These were real Strands agents on Gemini, writing real code, verified by real checks.{R}")
