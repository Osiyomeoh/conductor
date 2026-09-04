"""The verification runner.

This is the component that separates Conductor from a task tracker with a
language model bolted on. A worker moving an item to CLAIMED_DONE proves
nothing. This runner decides whether the claim survives contact with reality.
"""

from __future__ import annotations

import os
import urllib.request

from .models import Commitment, Evidence, EvidenceKind, Status, now


class VerificationRunner:
    def __init__(self, workdir: str = ".", timeout: int = 120, dry_run: bool = False,
                 runner=None):
        self.workdir = workdir
        self.timeout = timeout
        self.dry_run = dry_run
        # Where a command check runs: on the host, in a container, or in the
        # cloud. Chosen from the environment unless a runner is passed in.
        if runner is None:
            from .sandbox import runner_from_env
            runner = runner_from_env()
        self.runner = runner

    def verify(self, cm: Commitment) -> bool:
        ev = cm.evidence
        ev.checked_at = now()

        if ev.kind is EvidenceKind.NONE:
            # A commitment with no evidence requirement is a planning defect.
            # Fail closed rather than quietly believing the worker.
            ev.passed, ev.detail = False, "no evidence requirement defined at plan time"
        elif ev.kind is EvidenceKind.HUMAN_REVIEW:
            ev.passed, ev.detail = None, "requires a person"
        elif ev.kind is EvidenceKind.CI:
            # The repo's own CI is the judge. Stay pending until its result
            # arrives over the webhook; never believe the worker in the meantime.
            ev.passed, ev.detail = None, f"awaiting CI: {ev.spec or 'any required check'}"
        elif ev.kind is EvidenceKind.COMMAND:
            ev.passed, ev.detail = self._command(ev.spec)
        elif ev.kind is EvidenceKind.FILE_EXISTS:
            ev.passed, ev.detail = self._file(ev.spec)
        elif ev.kind is EvidenceKind.HTTP_OK:
            ev.passed, ev.detail = self._http(ev.spec)

        if ev.passed is True:
            cm.status = Status.DONE
            cm.log(f"verified: {ev.kind.value} `{ev.spec}` passed")
        elif ev.passed is False:
            cm.status = Status.REJECTED
            cm.log(f"REJECTED: {ev.kind.value} `{ev.spec}` -> {ev.detail}")
        else:
            cm.status = Status.VERIFYING
            cm.log("awaiting human verification")
        return ev.passed is True

    def _command(self, spec: str) -> tuple[bool, str]:
        if self.dry_run:
            return True, "dry run"
        # Delegated to the configured sandbox (local / docker / codebuild) so the
        # arbitrary check never runs in-process on the server by default in prod.
        return self.runner.run(self.workdir, spec, self.timeout)

    def _file(self, spec: str) -> tuple[bool, str]:
        path = os.path.join(self.workdir, spec)
        if not os.path.exists(path):
            return False, "path does not exist"
        if os.path.isfile(path) and os.path.getsize(path) == 0:
            return False, "file is empty"
        return True, f"{os.path.getsize(path)} bytes"

    def _http(self, spec: str) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(spec, timeout=self.timeout) as r:
                return (200 <= r.status < 400), f"HTTP {r.status}"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"


def evidence_quality(ev: Evidence) -> tuple[bool, str]:
    """Used by the planner to refuse its own weak plans."""
    if ev.kind is EvidenceKind.NONE:
        return False, "no evidence requirement"
    if ev.machine_checkable and not ev.spec.strip():
        return False, "evidence kind is machine checkable but no spec given"
    if ev.kind is EvidenceKind.COMMAND and ev.spec.strip() in {"true", ":", "echo ok"}:
        return False, "trivially passing command proves nothing"
    return True, "ok"
