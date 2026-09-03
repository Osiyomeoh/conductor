"""Policy and risk engine: AUTO / APPROVE / BLOCK.

Nothing Conductor wants to do reaches the world without passing here. This is
what makes an autonomous manager safe enough to actually leave running.
"""

from __future__ import annotations

from .models import Action, Decision, PolicyVerdict, Resource


class PolicyEngine:
    def __init__(self, autonomy: float = 0.6, max_auto_cost: float = 5.0):
        # autonomy 0.0 = ask about everything, 1.0 = only block the forbidden
        self.autonomy = autonomy
        self.max_auto_cost = max_auto_cost

    def evaluate(self, action: Action, actor: Resource | None = None) -> PolicyVerdict:
        reasons: list[str] = []
        risk = 0.0

        if action.irreversible:
            risk += 0.45
            reasons.append("irreversible")
        if action.external:
            risk += 0.25
            reasons.append("leaves the system")
        if action.kind in {"escalate"}:
            risk += 0.0
        if action.kind in {"reassign", "replan"}:
            risk += 0.10
        if action.cost_estimate > self.max_auto_cost:
            risk += 0.20
            reasons.append(f"cost {action.cost_estimate:.2f} over auto ceiling")
        if actor is not None and actor.reliability < 0.6:
            risk += 0.15
            reasons.append(f"worker reliability {actor.reliability:.0%}")

        # Hard blocks. These never proceed, at any autonomy setting.
        if action.payload.get("touches_production") or action.payload.get("touches_money"):
            reasons.append("touches production or money: humans only")
            return PolicyVerdict(Decision.BLOCK, 1.0, reasons)
        if action.payload.get("speaks_to_customer"):
            reasons.append("customer-facing speech requires a person")
            return PolicyVerdict(Decision.BLOCK, 0.9, reasons)

        risk = min(risk, 1.0)
        threshold = 0.25 + (self.autonomy * 0.5)
        decision = Decision.AUTO if risk <= threshold else Decision.APPROVE
        if not reasons:
            reasons.append("routine internal action")
        return PolicyVerdict(decision, risk, reasons)
