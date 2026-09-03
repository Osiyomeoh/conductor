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
DEFAULT_REGION = os.environ.get("CONDUCTOR_REGION", "us-west-2")

# Conductor runs agents that write files and execute commands. It must never
# borrow an ambient production identity because someone forgot to set a
# profile, so the profile is named explicitly and absent credentials fail loudly
# rather than silently falling through to `default`.
PROFILE = os.environ.get("CONDUCTOR_AWS_PROFILE", "conductor")


def strands_available() -> bool:
    try:
        import strands  # noqa: F401
        return True
    except ImportError:
        return False


def session():
    """An explicitly named boto session. Set CONDUCTOR_AWS_PROFILE="" to use the
    ambient credentials deliberately, for example inside AgentCore Runtime where
    the task role is the correct identity."""
    import boto3
    if not PROFILE:
        return boto3.Session(region_name=DEFAULT_REGION)
    try:
        return boto3.Session(profile_name=PROFILE, region_name=DEFAULT_REGION)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"AWS profile {PROFILE!r} not found. Create it with "
            f"`aws configure --profile {PROFILE}`, or set CONDUCTOR_AWS_PROFILE=''"
            f" to use ambient credentials on purpose."
        ) from e


def model(role: str = "orchestrator", override: str | None = None,
          temperature: float | None = None):
    """Bedrock-backed model for a role, bound to the Conductor profile.

    Cheap models do the volume, capable models do the judgment. Returns the
    model plus its resolved id, so cost accounting prices what actually ran
    rather than what the default said.
    """
    from strands.models import BedrockModel

    from ..models_config import for_role
    rm = for_role(role, override)
    temp = rm.temperature if temperature is None else temperature
    try:
        m = BedrockModel(model_id=rm.model_id, boto_session=session(),
                         temperature=temp)
    except TypeError:
        m = BedrockModel(boto_session=session(),
                         model_config={"model_id": rm.model_id, "temperature": temp})
    m.conductor_model_id = rm.model_id
    return m
