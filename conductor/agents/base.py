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

# Strands is model-agnostic. Bedrock is the intended provider for the AWS story,
# but when its token quota is starved a different provider gets a live agent
# running immediately. Set CONDUCTOR_PROVIDER=gemini (with GEMINI_API_KEY) to
# route every role to Gemini instead. The rest of the system does not change.
PROVIDER = os.environ.get("CONDUCTOR_PROVIDER", "bedrock").lower()


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
    """A model for a role, on the configured provider.

    Cheap models do the volume, capable models do the judgment. Returns the
    model tagged with its resolved id, so cost accounting prices what actually
    ran rather than what the default said.
    """
    from ..models_config import for_role
    rm = for_role(role, override)
    temp = rm.temperature if temperature is None else temperature

    if PROVIDER == "gemini":
        return _gemini(rm, temp)
    return _bedrock(rm, temp)


def _bedrock(rm, temp):
    from strands.models import BedrockModel
    try:
        m = BedrockModel(model_id=rm.model_id, boto_session=session(), temperature=temp)
    except TypeError:
        m = BedrockModel(boto_session=session(),
                         model_config={"model_id": rm.model_id, "temperature": temp})
    m.conductor_model_id = rm.model_id
    return m


def _gemini(rm, temp):
    """Gemini via Strands' native provider. The role's Bedrock model id is
    mapped to a Gemini equivalent: cheap for workers, capable for judgment."""
    from strands.models.gemini import GeminiModel

    from ..models_config import GEMINI_FOR_ROLE
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("CONDUCTOR_PROVIDER=gemini needs GEMINI_API_KEY set.")
    gid = GEMINI_FOR_ROLE.get(rm.role, "gemini-3.5-flash")
    m = GeminiModel(client_args={"api_key": key}, model_id=gid,
                    params={"temperature": temp})
    m.conductor_model_id = gid
    return m
