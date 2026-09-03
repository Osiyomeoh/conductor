"""Configuration, from the environment, in one place.

Production code reads config through here rather than scattering os.environ
across modules, so every setting has a name, a default, and a single point of
truth. Nothing secret is stored; secrets stay in the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Config:
    # model provider
    provider: str = os.environ.get("CONDUCTOR_PROVIDER", "bedrock").lower()
    region: str = os.environ.get("CONDUCTOR_REGION", "us-west-2")
    aws_profile: str = os.environ.get("CONDUCTOR_AWS_PROFILE", "conductor")

    # resilience: model calls hit rate limits and transient faults, so every
    # call retries with exponential backoff before it is allowed to fail.
    max_retries: int = _int("CONDUCTOR_MAX_RETRIES", 5)
    backoff_base: float = _float("CONDUCTOR_BACKOFF_BASE", 1.5)
    backoff_cap: float = _float("CONDUCTOR_BACKOFF_CAP", 30.0)
    model_timeout: int = _int("CONDUCTOR_MODEL_TIMEOUT", 120)

    # execution
    workspace_repo: str | None = os.environ.get("CONDUCTOR_REPO") or None
    verify_timeout: int = _int("CONDUCTOR_VERIFY_TIMEOUT", 300)

    # persistence: a DynamoDB table makes state durable; without one, a local
    # JSONL log is used, and in-memory when neither is available.
    dynamo_table: str | None = os.environ.get("CONDUCTOR_TABLE") or None
    event_log: str | None = os.environ.get("CONDUCTOR_EVENT_LOG") or None

    # server
    host: str = os.environ.get("CONDUCTOR_HOST", "127.0.0.1")
    port: int = _int("CONDUCTOR_PORT", 7616)
    tenant: str = os.environ.get("CONDUCTOR_TENANT", "default")

    def store(self):
        """The event store implied by the environment."""
        from .events import DynamoStore, JsonlStore, MemoryStore
        if self.dynamo_table:
            return DynamoStore(self.dynamo_table, region=self.region)
        if self.event_log:
            return JsonlStore(self.event_log)
        return MemoryStore()


CONFIG = Config()
