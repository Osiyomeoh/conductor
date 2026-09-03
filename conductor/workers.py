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
    def __init__(self, resource_id: str, workdir: str, competence: float = 0.7,
                 seed: int | None = None):
        self.id = resource_id
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
