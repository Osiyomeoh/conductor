"""Decision compressor.

Nine escalations usually hide two uncertainties. A tracker shows you nine
notifications and calls the short list "focus". Conductor finds the root
uncertainty, asks it once, and propagates the answer.

This is semantic work, so it is an agent. What it may do with the answer is not,
so that stays in the deterministic surface.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import model

SYSTEM = """You are given several escalations from a running project. Several
of them usually stem from the SAME underlying uncertainty, phrased differently.

Cluster them by root uncertainty. For each cluster, write ONE question that,
once answered, resolves every escalation in it. The question must be answerable
in under twenty seconds by a busy person who has not been following along:
concrete, closed, with real options. Never ask an open question. Never ask for
context the person would have to go and gather.

Return the smallest number of clusters that is honest. Do not merge two genuinely
different uncertainties to look efficient."""


class Cluster(BaseModel):
    root_question: str
    options: list[str] = Field(min_length=2)
    uncertainty_key: str = Field(description="short stable slug for this uncertainty")
    escalation_ids: list[str]
    rationale: str = ""


class Compression(BaseModel):
    clusters: list[Cluster]


class CompressorAgent:
    def __init__(self):
        from strands import Agent
        self.agent = Agent(model=model(0.1), system_prompt=SYSTEM, name="compressor",
                           description="Collapses many escalations into few root questions")

    def compress(self, escalations: list[dict]) -> Compression:
        lines = "\n".join(
            f"- id={e['id']} | {e['question']} | blocks {e.get('blocks', 0)} items"
            for e in escalations)
        return self.agent.structured_output(Compression, f"Escalations:\n{lines}")
