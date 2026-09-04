"""Consequence signals: which work touches production, money, or a customer.

The policy engine hard-blocks those, but something has to recognize them. This
reads a commitment's own description and classifies it, so a deploy, a migration,
a refund, or a customer email is escalated to a human rather than run by an
agent. Patterns are extendable per deployment via env, because "production" looks
different in every org.
"""

from __future__ import annotations

import os

_PRODUCTION = ("deploy", "production", " prod", "migration", "migrate", "terraform",
               ".tf", "kubernetes", "k8s", "dockerfile", "infra", "release",
               "rollout", "dns", "load balancer", "secret", "credential")
_MONEY = ("payment", "charge", "refund", "billing", "invoice", "payout", "stripe",
          "transfer funds", "wire", "withdraw", "subscription price")
_CUSTOMER = ("email customer", "customer email", "email the customer", "announce",
             "press release", "publish post", "tweet", "post to", "customer-facing",
             "notify users", "send to users")


def _env_patterns(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(p.strip().lower() for p in raw.split(",") if p.strip())


def classify(cm) -> dict:
    """Flags for the policy engine, from what the commitment says it will do.

    Off by default (the seeded demo runs its own scripted flow); enable the full
    keyword detection with CONDUCTOR_SIGNALS=1 in a real deployment, where a
    deploy or a refund really must escalate. The default preserves the original
    conservative behaviour: only an explicitly consequential, not-yet-isolated
    commitment is treated as production-touching."""
    if os.environ.get("CONDUCTOR_SIGNALS", "0") != "1":
        return {"touches_production": bool(getattr(cm, "consequential", False))
                and not getattr(cm, "branch", None)}

    text = " ".join(filter(None, [
        getattr(cm, "title", ""), getattr(cm, "artifact_path", "") or "",
        getattr(cm, "work_kind", ""),
        getattr(getattr(cm, "evidence", None), "spec", "") or ""])).lower()

    def hit(base: tuple[str, ...], env: str) -> bool:
        return any(p in text for p in base) or any(p in text for p in _env_patterns(env))

    return {
        # An explicitly consequential commitment counts as production-touching too.
        "touches_production": bool(getattr(cm, "consequential", False))
                              or hit(_PRODUCTION, "CONDUCTOR_PRODUCTION_PATTERNS"),
        "touches_money": hit(_MONEY, "CONDUCTOR_MONEY_PATTERNS"),
        "speaks_to_customer": hit(_CUSTOMER, "CONDUCTOR_CUSTOMER_PATTERNS"),
    }
