"""Run the UI against a LIVE agent workspace.

    set -a && . ./.env && set +a
    CONDUCTOR_PROVIDER=gemini python serve_live.py

Opens the app on a real git repo with a live Strands worker (Gemini by
default). Nothing runs until you drive it from the UI — click 'Run six' or
'Advance tick' — so the free-tier quota is spent deliberately, not by the
4-second poll. Watch real code get written, verified in a worktree, and merged.
"""
import os, tempfile

os.environ.setdefault("CONDUCTOR_PROVIDER", "gemini")
from conductor.realworld import build
from conductor.server import serve

repo = os.environ.get("CONDUCTOR_REPO") or os.path.join(tempfile.mkdtemp(), "workspace")
c = build(repo, live=True)
print(f"LIVE workspace at {repo}  (provider: {os.environ['CONDUCTOR_PROVIDER']})")
print("Nothing runs until you click Run in the UI.")
serve(c, port=7616)
