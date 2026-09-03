"""Run Conductor's UI with durable state.

    python serve.py

State persists through the store the environment selects (CONDUCTOR_TABLE for
DynamoDB, CONDUCTOR_EVENT_LOG for a local JSONL file, in-memory otherwise). On
restart the server resumes the work and trust the previous process left.
"""
from conductor.config import CONFIG
from conductor.logging_setup import setup
from conductor.server import serve
from conductor.world import persistent

setup()
c = persistent(store=CONFIG.store(), tenant=CONFIG.tenant)
if not c.graph.commitments:
    c.run(ticks=1)   # nudge a fresh workspace so the board is not empty
serve(c, port=CONFIG.port)
