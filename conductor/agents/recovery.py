"""Recovery agent.

A failed verification is a fact plus a reason. The fact is deterministic. The
reason is a diagnosis, and diagnosis is judgment: did the worker misread the
requirement, was the evidence check wrong, or is the task actually beyond it?

Getting this right is what stops the loop from re-dispatching the same failure
three times and then wasting a human's attention on it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import model

SYSTEM = """A worker claimed a task was complete. The evidence check failed.

Decide what actually went wrong and what should happen next. Be willing to
conclude that the CHECK was wrong rather than the work: a badly written proof
is a planning defect, and re-dispatching against it will fail forever.

Choose one action:
- retry: re-dispatch to the same worker with the failure detail as context
- reassign: a different worker, or a human
- fix_evidence: the check itself is wrong; state the corrected check
- escalate: a person must decide; give the options

Be concise and specific. The retry context you write is the only thing the
worker will see about why it failed."""


class Diagnosis(BaseModel):
    cause: str
    action: str = Field(description="retry | reassign | fix_evidence | escalate")
    retry_context: str = ""
    corrected_evidence_spec: str = ""
    escalation_question: str = ""
    escalation_options: list[str] = Field(default_factory=list)


class RecoveryAgent:
    def __init__(self):
        from strands import Agent
        self.agent = Agent(model=model("recovery"), system_prompt=SYSTEM, name="recovery",
                           description="Diagnoses failed verifications and decides the next move")

    def diagnose(self, title: str, evidence_spec: str, detail: str,
                 attempts: int, worker: str, trust: float) -> Diagnosis:
        from ..resilience import with_retry
        from ..config import CONFIG
        prompt = f"""Task: {title}
Evidence check: {evidence_spec}
Failure detail: {detail}
Attempt: {attempts}
Worker: {worker} (trust on this kind of work: {trust:.0%})"""
        return with_retry(lambda: self.agent.structured_output(Diagnosis, prompt),
                          max_retries=CONFIG.max_retries, base=CONFIG.backoff_base,
                          cap=CONFIG.backoff_cap)
