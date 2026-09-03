"""Model selection, per role.

The cost curve is not spread evenly across the system. Judgment agents run a
handful of times per tick; worker agents run on every dispatched commitment,
multiplied by every speculation branch. So paying the same rate for both is
simply a mistake.

Roles are priced by what they actually need:

  planner     writes the check whose failure must be meaningful. This is the
              hardest judgment in the system and a weak model here launders
              false claims into green ticks. Pay for it.
  recovery    diagnoses failure, including ruling that the CHECK was wrong.
  compressor  finds the uncertainty behind many escalations.
  orchestrator routes and arbitrates.
  worker      volume. The entire cost curve lives here.

Any role can be overridden by environment variable, and an AgentSpec can pin
its own model, so a docs agent and a migration agent need not cost the same.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Gemini equivalents per role: Flash for volume, Pro for judgment. Used when
# CONDUCTOR_PROVIDER=gemini. Prices below are Bedrock's; Gemini spend shows as
# its own model ids in the ledger and is priced separately when it matters.
GEMINI_FOR_ROLE = {
    "planner": "gemini-3.1-pro-preview",
    "recovery": "gemini-3.1-pro-preview",
    "compressor": "gemini-3.1-pro-preview",
    "orchestrator": "gemini-3.1-pro-preview",
    "worker": "gemini-3.5-flash",
}
GEMINI_PRICES = {
    "gemini-3.5-flash": (0.30, 2.50),
    "gemini-3.1-pro-preview": (1.25, 10.00),
}

SONNET = "global.anthropic.claude-sonnet-4-6"
HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# USD per million tokens, input/output. Placeholders until measured.
PRICES: dict[str, tuple[float, float]] = {
    SONNET: (3.00, 15.00),
    HAIKU: (1.00, 5.00),
    "default": (3.00, 15.00),
}

PRICES.update(GEMINI_PRICES)

ROLE_DEFAULTS: dict[str, str] = {
    "planner": SONNET,
    "recovery": SONNET,
    "compressor": SONNET,
    "orchestrator": SONNET,
    "worker": HAIKU,
}

ROLE_TEMPERATURE: dict[str, float] = {
    "planner": 0.2,
    "recovery": 0.2,
    "compressor": 0.1,     # clustering should be stable across runs
    "orchestrator": 0.2,
    "worker": 0.2,
}


@dataclass(frozen=True)
class RoleModel:
    role: str
    model_id: str
    temperature: float

    @property
    def price(self) -> tuple[float, float]:
        return PRICES.get(self.model_id, PRICES["default"])


def for_role(role: str, override: str | None = None) -> RoleModel:
    """Resolution order: explicit override (an AgentSpec pinning its own model),
    then CONDUCTOR_MODEL_<ROLE>, then CONDUCTOR_MODEL for everything, then the
    role default."""
    model_id = (
        override
        or os.environ.get(f"CONDUCTOR_MODEL_{role.upper()}")
        or os.environ.get("CONDUCTOR_MODEL")
        or ROLE_DEFAULTS.get(role, SONNET)
    )
    return RoleModel(role=role, model_id=model_id,
                     temperature=ROLE_TEMPERATURE.get(role, 0.2))


def table() -> str:
    rows = []
    for role in ROLE_DEFAULTS:
        rm = for_role(role)
        pin, pout = rm.price
        rows.append(f"  {role:<13} {rm.model_id:<46} ${pin}/${pout} per Mtok")
    return "\n".join(rows)
