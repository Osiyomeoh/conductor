"""Strands wiring.

Conductor's split: language models do the judgment, deterministic code does the
gating. Planning, clustering and diagnosis are genuinely ambiguous and belong
to agents. Policy, verification, attention and trust are consequential and must
be auditable, so they stay as code. An agent never decides whether something is
done.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = os.environ.get("CONDUCTOR_MODEL", "global.anthropic.claude-sonnet-4-6")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-west-2")


def strands_available() -> bool:
    try:
        import strands  # noqa: F401
        return True
    except ImportError:
        return False


def model(temperature: float = 0.2):
    """Bedrock-backed model. Falls back to the plain id string if the provider
    class moves, which keeps the import surface small."""
    from strands.models import BedrockModel
    try:
        return BedrockModel(model_id=DEFAULT_MODEL, region_name=DEFAULT_REGION,
                            temperature=temperature)
    except TypeError:
        return BedrockModel(region_name=DEFAULT_REGION,
                            model_config={"model_id": DEFAULT_MODEL,
                                          "temperature": temperature})
