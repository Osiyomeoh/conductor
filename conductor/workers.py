"""Workers Conductor can actually command.

A manager that only observes is a dashboard. Conductor dispatches, reads what
came back, verifies it against reality, and re-dispatches on failure.

`SimulatedWorker` is not a mock verdict generator. It produces real artifacts
on disk, and the verification runner checks them with real commands. Its
failure mode is the one that matters: confident, plausible, and wrong. Silence
is easy to catch; this is not.
"""

from __future__ import annotations

import os
import random
from typing import Protocol


from .models import Commitment, Status, now


class Worker(Protocol):
    id: str
    def dispatch(self, cm: Commitment, context: str = "") -> None: ...


class SimulatedWorker:
    # Rough shape of a real coding dispatch, used only when no model ran.
    EST_INPUT, EST_OUTPUT = 45_000, 8_000

    def __init__(self, resource_id: str, workdir: str, competence: float = 0.7,
                 seed: int | None = None, ledger=None):
        self.id = resource_id
        self.ledger = ledger
        self.workdir = workdir
        self.competence = competence
        self.rng = random.Random(seed)

    def dispatch(self, cm: Commitment, context: str = "") -> None:
        cm.attempts += 1
        cm.owner = self.id
        cm.status = Status.DISPATCHED
        cm.last_signal = now()
        cm.log(f"dispatched to {self.id} (attempt {cm.attempts})")

        # A retry carries the failure detail back, so it usually lands.
        p = min(self.competence + (0.3 if cm.attempts > 1 else 0.0), 0.97)
        correct = self.rng.random() < p

        artifact = cm.artifact_path or f"{cm.id}.txt"
        path = os.path.join(self.workdir, artifact)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            if correct:
                f.write(f"{cm.expected_token}\nimplemented: {cm.title}\n")
            else:
                # Plausible. Well formatted. Missing the thing that was asked for.
                f.write(f"implemented: {cm.title}\nnotes: complete and working\n")

        if self.ledger is not None:
            jitter = 0.7 + self.rng.random() * 0.6
            from .models_config import for_role
            e = self.ledger.record(cm, self.id, for_role("worker").model_id,
                                   int(self.EST_INPUT * jitter),
                                   int(self.EST_OUTPUT * jitter))
            cm.log(f"spent ${e.usd:.4f}")
        cm.status = Status.CLAIMED_DONE
        cm.last_signal = now()
        cm.log(f"{self.id} reports complete -> {artifact}")


class SilentWorker(SimulatedWorker):
    """Takes the work and says nothing. The easy failure, still worth catching."""

    def dispatch(self, cm: Commitment, context: str = "") -> None:
        cm.attempts += 1
        cm.owner = self.id
        cm.status = Status.DISPATCHED
        cm.last_signal = now()
        cm.log(f"dispatched to {self.id}; no response")


class StrandsWorker:
    """A real agent teammate, built from its AgentSpec at dispatch time.

    Note what it is NOT allowed to do: it has no tool for reporting success. It
    does the work, writes its artifact, and its claim is just a claim. The
    verification runner decides, afterwards, whether the claim survives. An
    agent that could mark its own work done would reintroduce exactly the
    failure this whole system exists to catch.
    """

    def __init__(self, resource, workdir: str = ".", tools: list | None = None,
                 ledger=None, executor=None):
        self.id = resource.id
        self.ledger = ledger
        self.resource = resource
        self.workdir = workdir
        self.extra_tools = tools or []
        self.executor = executor   # when set, open a real worktree per dispatch
        self._agent = None

    def _build(self):
        from strands import Agent, tool

        from .agents.base import model

        worker = self  # tools resolve the CURRENT worktree, not a fixed one

        @tool
        def write_artifact(path: str, content: str) -> str:
            """Write your output to a file inside the working directory."""
            full = os.path.join(worker.workdir, path)
            os.makedirs(os.path.dirname(full) or worker.workdir, exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
            return f"wrote {len(content)} bytes to {path}"

        @tool
        def read_artifact(path: str) -> str:
            """Read a file inside the working directory."""
            full = os.path.join(worker.workdir, path)
            if not os.path.exists(full):
                return f"{path} does not exist"
            with open(full) as f:
                return f.read()[:8000]

        spec = self.resource.spec
        scopes = ", ".join(self.resource.scopes) or "none"
        principal = (f"\nYou act on behalf of {self.resource.principal}. Never take an "
                     f"action they would not sanction." if self.resource.principal else "")
        m = model("worker", override=spec.model if spec else None)
        self.model_id = getattr(m, "conductor_model_id", "default")
        return Agent(
            model=m,
            name=self.id,
            description=spec.purpose if spec else "worker",
            system_prompt=(
                f"{spec.purpose if spec else 'Complete the assigned task.'}\n"
                f"Permitted scopes: {scopes}.{principal}\n\n"
                "You will be given one work order and the exact check that will "
                "be run against your output afterwards. Satisfy the check "
                "honestly: do the work it describes, not the minimum that would "
                "make it pass. You cannot mark your own work complete and you "
                "will not be asked to assess it."
            ),
            tools=[write_artifact, read_artifact, *self.extra_tools],
        )

    def dispatch(self, cm, context: str = "") -> None:
        if self.executor is not None and cm.branch:
            # Real isolation: the agent writes into this commitment's worktree.
            self.workdir = self.executor.open(cm.branch)
        if self._agent is None:
            self._agent = self._build()
        cm.attempts += 1
        cm.owner = self.id
        cm.status = Status.DISPATCHED
        cm.last_signal = now()
        cm.log(f"dispatched to {self.id} (attempt {cm.attempts})")

        order = (f"Work order: {cm.title}\n"
                 f"Write your output to: {cm.artifact_path}\n"
                 f"The check that will be run afterwards: {cm.evidence.spec}\n"
                 f"{('Previous attempt failed: ' + context) if context else ''}")
        try:
            from .resilience import with_retry
            from .config import CONFIG
            result = with_retry(lambda: self._agent(order),
                                max_retries=CONFIG.max_retries,
                                base=CONFIG.backoff_base, cap=CONFIG.backoff_cap)
            # Real measured usage, not an estimate.
            if self.ledger is not None:
                u = getattr(getattr(result, "metrics", None), "accumulated_usage", {}) or {}
                e = self.ledger.record(
                    cm, self.id, getattr(self, "model_id", "default"),
                    int(u.get("inputTokens", 0)), int(u.get("outputTokens", 0)))
                cm.log(f"spent ${e.usd:.4f} "
                       f"({e.input_tokens}in/{e.output_tokens}out)")
            cm.status = Status.CLAIMED_DONE
            cm.log(f"{self.id} reports complete")
        except Exception as e:  # noqa: BLE001
            cm.status = Status.REJECTED
            cm.evidence.passed = False
            cm.evidence.detail = f"worker error: {type(e).__name__}: {e}"
            cm.log(f"{self.id} failed to run: {e}")
        cm.last_signal = now()
