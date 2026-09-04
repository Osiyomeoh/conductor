"""Outcome metrics: the raw material of verifying reality, not just work.

At 1000x a commitment is not done when its code merges; it is done when the
metric it was meant to move actually moved. This module reads a metric from a
source and evaluates an outcome spec against it, so the verification runner can
treat "signup_completion >= 0.4" as evidence the same way it treats a test.

A source is anything that answers value(metric) -> float | None. In-memory here
for tests and the demo; a real deployment points it at analytics, CloudWatch, or
a metrics webhook feed behind the same one method.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field

_OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt,
        "<": operator.lt, "==": operator.eq}
_SPEC = re.compile(r"^\s*([A-Za-z0-9_.:-]+)\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_outcome(spec: str):
    """('signup_completion', '>=', 0.4) from a spec string, or None if malformed."""
    m = _SPEC.match(spec or "")
    if not m:
        return None
    return m.group(1), m.group(2), float(m.group(3))


@dataclass
class MemoryMetricSource:
    """Metric values held in memory. `set` reports a value; `value` reads it."""
    values: dict = field(default_factory=dict)

    def set(self, metric: str, v: float) -> None:
        self.values[metric] = v

    def value(self, metric: str):
        return self.values.get(metric)


def evaluate(spec: str, source) -> tuple[bool | None, str]:
    """Verdict on an outcome spec against a source.

    True  = the target is met (the outcome is real).
    None  = not met yet, or not reported yet. An unmet outcome is NOT a failure:
            the work may be correct and the metric simply hasn't moved, so it
            stays pending (watched), never rejected as a lie.
    """
    parsed = parse_outcome(spec)
    if parsed is None:
        return False, f"malformed outcome spec: {spec!r}"
    metric, op, target = parsed
    v = source.value(metric) if source is not None else None
    if v is None:
        return None, f"{metric} not reported yet (target {op} {target})"
    if _OPS[op](v, target):
        return True, f"{metric}={v} meets {op} {target}"
    return None, f"{metric}={v}, target {op} {target} not reached yet"
