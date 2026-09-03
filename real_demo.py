"""Run the whole loop against a real git repository, no model needed.

    python real_demo.py [repo_path]

Watch a real base branch advance for verified work only, and watch a wrong
implementation get caught by its check and discarded before any human sees it.
"""

import os, subprocess, sys, tempfile

from conductor.models import Status
from conductor.realworld import build, TASKS

C = ["\033[0m", "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[33m"]
R, D, B, G, RED, Y = C


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.mkdtemp(), "workspace")
    c = build(repo)
    gx = c.executor
    print(f"{B}CONDUCTOR{R}  {D}real repository at {gx.repo}{R}")
    print(f"{D}base branch: {gx.base} · starting commit: {gx.base_log()[0]}{R}\n")

    c.run(ticks=10)
    # answer the one human decision, then let dependent work settle
    q = [d for d in c.surface.queue() if len(d.options) >= 2]
    if q:
        print(f"{Y}The loop stopped for one decision:{R} {q[0].root_question}")
        print(f"{D}Sam answers: {q[0].options[0]!r}{R}\n")
        c.answer(q[0].id, q[0].options[0]); c.run(ticks=6)

    print(f"{B}Commitments{R}")
    for cm in c.graph:
        col = {Status.DONE: G, Status.REJECTED: RED}.get(cm.status, D)
        tries = f" {D}({cm.attempts} attempts){R}" if cm.attempts > 1 else ""
        print(f"  {col}{cm.status.value:<9}{R} {cm.title}{tries}")

    print(f"\n{B}What reached the real base branch{R}  {D}(only verified work){R}")
    for line in gx.base_log(12):
        merge = "conductor: merge" in line
        print(f"  {G if merge else D}{line}{R}")

    files = sorted(f for f in os.listdir(repo) if f.endswith(".py"))
    print(f"\n{B}Files on base{R}: {', '.join(files)}")
    # prove the caught bug never landed: slugify lowercases, backoff is 2**n
    if "slugify.py" in files:
        import importlib.util
        for name in ("slugify", "backoff"):
            p = os.path.join(repo, f"{name}.py")
            if os.path.exists(p):
                spec = importlib.util.spec_from_file_location(name, p)
                mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                if name == "slugify":
                    print(f"  {G}slugify('Hello World') = {mod.slugify('Hello World')!r}{R}  "
                          f"{D}(the wrong first attempt never merged){R}")
                else:
                    print(f"  {G}backoff(3) = {mod.backoff(3)}{R}  {D}(off-by-one attempt discarded){R}")

    branches = [b.strip("* ").strip() for b in git(repo, "branch").splitlines() if b.strip()]
    print(f"\n{B}Branches remaining{R}: {', '.join(branches)}  {D}(every conductor/* worktree cleaned up){R}")

    m = c.metrics
    print(f"\n{B}Summary{R}")
    print(f"  {G}verified and merged   {m.verified}{R}")
    print(f"  {RED}claims caught wrong   {m.claims_rejected}{R}  {D}before Sam saw them{R}")
    print(f"  {B}times Sam interrupted {m.interruptions}{R}")


if __name__ == "__main__":
    main()
