"""Run Conductor as a production ASGI service.

    python serve.py                     # or: uvicorn conductor.asgi:app

Per-tenant isolation, durable state, an auth boundary and request logging come
from conductor.asgi. Configuration is read from the environment (see
conductor/config.py): CONDUCTOR_PROVIDER, CONDUCTOR_TABLE / CONDUCTOR_EVENT_LOG,
CONDUCTOR_REQUIRE_AUTH, CONDUCTOR_HOST / CONDUCTOR_PORT.
"""
import uvicorn

from conductor.config import CONFIG
from conductor.logging_setup import setup

if __name__ == "__main__":
    setup()
    uvicorn.run("conductor.asgi:app", host=CONFIG.host, port=CONFIG.port,
                log_level="info")
