"""The control loop.

Trackers record work. Conductor runs a closed loop whose objective is the
human's attention and whose lever is cheap parallel labour:

    observe -> verify -> recover -> compress -> speculate -> dispatch

Every tick is idempotent and every state change is appended to an event log,
so the loop is resumable and the whole run is replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .decisions import DecisionSurface
from .events import EventKind, Recorder
from .dispatcher import Dispatcher
from .models import Status, now
from .speculation import SpeculationEngine
from .cost import CostLedger
from .trust import TrustLedger
from .verification import VerificationRunner


@dataclass
class Metrics:
    dispatched: int = 0
    claims: int = 0
    claims_rejected: int = 0
    verified: int = 0
    escalations_raised: int = 0
    questions_asked: int = 0
    interruptions: int = 0
    speculative_cost: float = 0.0
    cost_verified: float = 0.0
    cost_rejected: float = 0.0
    held: int = 0


@dataclass
class Conductor:
    graph: object
    verifier: VerificationRunner
    dispatcher: Dispatcher
    surface: DecisionSurface
    speculation: SpeculationEngine
    trust: TrustLedger
    cost: CostLedger = field(default_factory=CostLedger)
    recorder: Recorder = field(default_factory=Recorder)
    events: list[str] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    silence_hours: float = 4.0
    executor: object = None  # GitExecutor for real mode; None = scratch-dir demo
    cost_ceiling: float = 0.0  # hard spend cap; 0 = unlimited. Over it, work holds.

    def emit(self, msg: str) -> None:
        self.events.append(f"{now().isoformat(timespec='seconds')}  {msg}")

    def record(self, kind: EventKind, **kw):
        """Every meaningful transition becomes a durable fact. The readable log
        above is for humans; this one is the state."""
        return self.recorder.record(kind, **kw)

    # ------------------------------------------------------------------
    def tick(self) -> None:
        self._verify_claims()
        self._watch_outcomes()
        self._recover()
        self._surface_judgment()
        self._compress()
        self._speculate()
        self._dispatch()

    def _watch_outcomes(self) -> None:
        """Verify reality, and that it stays true. An outcome commitment is only
        done once its metric has held the target for a few checks; if a done
        outcome later regresses, roll the change back and reopen it. This is what
        makes 'done' mean the metric moved and stayed moved, not just merged."""
        from .metrics import evaluate
        from .models import EvidenceKind
        src = getattr(self.verifier, "metric_source", None)
        for cm in self.graph:
            if cm.evidence.kind is not EvidenceKind.OUTCOME:
                continue
            # Watched from creation: pending outcomes start watching immediately.
            if cm.status not in (Status.PENDING, Status.VERIFYING, Status.WATCHING, Status.DONE):
                continue
            from .learning import attach as _attach
            from .metrics import parse_outcome
            met, detail = evaluate(cm.evidence.spec, src)
            need = getattr(cm, "hold_required", 2)
            streak = getattr(cm, "hold_streak", 0)
            _metric = (parse_outcome(cm.evidence.spec) or ("_",))[0]
            if met is True:
                cm.hold_streak = streak + 1
                if cm.hold_streak >= need:
                    if cm.status is not Status.DONE:
                        cm.status, cm.evidence.passed, cm.evidence.detail = Status.DONE, True, detail
                        cm.log(f"outcome held {cm.hold_streak}x: {detail}")
                        _attach(self).record(_metric, True)     # reality's verdict: held
                        self.record(EventKind.VERIFIED, commitment_id=cm.id, note="outcome")
                else:
                    cm.status = Status.WATCHING
                    cm.log(f"outcome met ({cm.hold_streak}/{need}); watching")
            elif cm.status is Status.DONE:
                # Reality reversed after we believed it: reopen and roll back.
                cm.status, cm.evidence.passed = Status.REJECTED, False
                cm.evidence.detail = f"regressed: {detail}"
                cm.hold_streak = 0
                cm.log(f"outcome regressed, rolling back: {detail}")
                _attach(self).record(_metric, False)         # reality's verdict: regressed
                self._rollback(cm)
                self.record(EventKind.REJECTED, commitment_id=cm.id, note="regression")
            else:
                cm.hold_streak, cm.status = 0, Status.WATCHING

    def _rollback(self, cm) -> None:
        ex = self.executor
        if ex is not None and getattr(cm, "branch", None) and hasattr(ex, "revert"):
            try:
                _ok, detail = ex.revert(cm.branch)
                cm.log(f"rollback: {detail}")
            except Exception as e:  # noqa: BLE001
                cm.log(f"rollback failed: {e}")
        self.emit(f"rolled back {cm.id} after outcome regression")

    def resume(self) -> int:
        """Fold the durable log back over the graph. The loop restarts from the
        facts, not from a snapshot that might disagree with them."""
        from .replay import rebuild
        self.recorder.replaying = True
        try:
            return rebuild(self.graph, self.recorder.history())
        finally:
            self.recorder.replaying = False

    def run(self, ticks: int = 12) -> None:
        for _ in range(ticks):
            self.tick()
            if not self._work_remaining():
                break

    def _work_remaining(self) -> bool:
        return any(c.status not in (Status.DONE, Status.BLOCKED) for c in self.graph)

    # ------------------------------------------------------------------
    def _verify_claims(self) -> None:
        """Done is a claim, not a fact. This is where claims meet reality.

        With a real executor, the check runs inside the commitment's git
        worktree and a pass is a real merge, a fail a real discard. Without one,
        the verifier runs against the shared scratch dir (the deterministic
        demo path). Either way, the verdict comes from running the evidence,
        never from the worker's word."""
        for cm in self.graph.claimed():
            self.metrics.claims += 1
            passed = self._verify_one(cm)
            self.trust.record(cm.owner, cm.work_kind, passed)
            worker = self.graph.resources.get(cm.owner or "")
            if worker:
                worker.record_claim(passed)
            budget = self.dispatcher.budget_for(cm.reviewer or "")
            # A rejected claim costs the human nothing. That is the point.
            budget.release(cm, consumed=passed)
            self.cost.settle(cm.id, "verified" if passed else "rejected")
            self.record(EventKind.CLAIMED, commitment_id=cm.id, actor=cm.owner)
            if passed:
                self.metrics.verified += 1
                self.record(EventKind.VERIFIED, commitment_id=cm.id, actor=cm.owner,
                            detail=cm.evidence.detail[:200], branch=cm.branch)
                if cm.branch:
                    self.emit(f"MERGE {cm.branch} <- verified: {cm.title}")
            else:
                self.metrics.claims_rejected += 1
                self.record(EventKind.REJECTED, commitment_id=cm.id, actor=cm.owner,
                            detail=cm.evidence.detail[:200], attempt=cm.attempts)
                self.emit(f"REJECT {cm.title}: {cm.evidence.detail[:90]}")

    def _verify_one(self, cm) -> bool:
        """Run a commitment's evidence, in its real worktree when there is one."""
        from .models import EvidenceKind, Status, now
        ex = self.executor
        if ex is None or cm.branch is None or cm.evidence.kind is not EvidenceKind.COMMAND:
            return self.verifier.verify(cm)

        # Real path: commit the worker's output, run the check in the worktree.
        ex.commit(cm.branch, f"{cm.owner or 'worker'}: {cm.title}")
        cm.evidence.checked_at = now()
        ok, detail = ex.verify_in(cm.branch, cm.evidence.spec)
        cm.evidence.passed, cm.evidence.detail = ok, detail
        if ok:
            merged, mdetail = ex.merge(cm.branch)
            cm.status = Status.DONE
            cm.evidence.detail = f"verified and {mdetail}"
            cm.log(f"verified in {cm.branch}, merged to base")
        else:
            ex.discard(cm.branch)   # wrong work leaves no trace on the base
            cm.status = Status.REJECTED
            cm.log(f"REJECTED in {cm.branch}, worktree discarded: {detail[:80]}")
        return ok

    def _recover(self) -> None:
        """Graduated protocols. Rejected work goes back with the failure as
        context; silence escalates by stages; repeated failure becomes a
        question for a human."""
        for cm in self.graph:
            if cm.status is Status.REJECTED:
                if cm.attempts >= 3:
                    self._escalate(cm,
                        f"{cm.title} has failed verification {cm.attempts} times",
                        ["reassign to a human", "reduce scope", "drop it"],
                        key=f"repeat-failure:{cm.work_kind}")
                else:
                    cm.status = Status.PENDING
                    cm.log(f"recovery: re-dispatch with failure context "
                           f"({cm.evidence.detail[:60]})")
            elif cm.status is Status.DISPATCHED:
                hours = cm.silent_for / timedelta(hours=1)
                if hours >= self.silence_hours * 3 and cm.recovery_stage < 2:
                    cm.recovery_stage = 2
                    self._escalate(cm, f"{cm.title} has been silent for {hours:.0f}h",
                                   ["reassign to an agent", "extend", "drop"],
                                   key=f"silence:{cm.owner}")
                elif hours >= self.silence_hours and cm.recovery_stage < 1:
                    cm.recovery_stage = 1
                    cm.log("recovery stage 1: soft status request sent")

    def _escalate(self, cm, question: str, options: list[str], key: str) -> None:
        self.metrics.escalations_raised += 1
        cm.status = Status.ESCALATED
        d = self.surface.raise_question(question, options, key, cm.id)
        cm.log(f"escalated into {d.id}")
        self.record(EventKind.ESCALATED, commitment_id=cm.id, decision_id=d.id,
                    question=question, options=options)

    def _compress(self) -> None:
        self.metrics.questions_asked = len(self.surface.open) + len(self.surface.answered)

    def _speculate(self) -> None:
        """Do not wait on the human. Build every plausible answer meanwhile."""
        for d in self.surface.queue():
            if len(d.options) < 2:
                # Nothing plausible to fork across. The Compressor proposes real
                # options when it has enough context; until then, wait honestly.
                continue
            if any(b.decision_id == d.id for b in self.speculation.branches.values()):
                continue
            if self.speculation.budget_exhausted(d.id):
                continue
            made = self.speculation.fork(d, self._speculative_plan)
            if made:
                self.record(EventKind.SPECULATED, decision_id=d.id,
                            branches=[b.id for b in made])
                self.emit(f"SPEC  {d.id} forked into {len(made)} branches while waiting")

    def _speculative_plan(self, option: str, blocked_cm):
        """Planner hook: what becomes possible if this answer holds."""
        from .models import Commitment, Evidence, EvidenceKind
        token = f"SPEC_{abs(hash(option)) % 9973}"
        short = option if len(option) <= 32 else option[:29] + "..."
        cm = Commitment.new(
            title=f"[{short}] follow-on work",
            evidence=Evidence(EvidenceKind.COMMAND,
                              spec=f"grep -q {token} spec_{blocked_cm.id}.txt",
                              description=f"artifact proves the {option} path"),
            work_kind=blocked_cm.work_kind, review_cost_minutes=5)
        cm.artifact_path = f"spec_{blocked_cm.id}.txt"
        cm.expected_token = token
        return [cm]

    def _surface_judgment(self) -> None:
        """A judgment call is not work. It is a question. Dispatching it to a
        human and watching it sit in `held` is the mistake every tracker makes:
        it models the decision as a task with an assignee and a due date."""
        for cm in self.graph.ready():
            if cm.ambiguous and cm.status is not Status.ESCALATED:
                # Placeholder options are worse than none: they make an
                # unanswerable question look answerable, and speculation would
                # then spend real money building "option A".
                self._escalate(cm, cm.title, cm.options, key=f"judgment:{cm.id}")

    def _dispatch(self) -> None:
        from .models import EvidenceKind
        # Cost governance: at or over the ceiling, stop spending. Ready work is
        # held with the reason rather than dispatched, so a runaway can only ever
        # cost up to the ceiling, and the held work resumes if the ceiling lifts.
        over_budget = self.cost_ceiling > 0 and self.cost.total >= self.cost_ceiling
        for cm in self.graph.ready():
            if cm.evidence.kind is EvidenceKind.OUTCOME:
                continue        # outcomes are watched, never dispatched to a worker
            if over_budget:
                cm.status = Status.HELD
                self.metrics.held += 1
                cm.log(f"held: spend ceiling ${self.cost_ceiling:.2f} reached")
                self.record(EventKind.HELD, commitment_id=cm.id,
                            reason=f"spend ceiling ${self.cost_ceiling:.2f} reached")
                continue
            if self.dispatcher.dispatch(cm):
                self.metrics.dispatched += 1
                self.record(EventKind.DISPATCHED, commitment_id=cm.id,
                            actor=cm.owner, attempt=cm.attempts)
            elif cm.status is Status.HELD:
                self.metrics.held += 1
                self.record(EventKind.HELD, commitment_id=cm.id,
                            reviewer=cm.reviewer, cost=cm.review_cost_minutes)

    # ------------------------------------------------------------------
    def answer(self, decision_id: str, choice: str) -> None:
        """The human spends attention. Everything downstream resolves at once."""
        self.metrics.interruptions += 1
        d = self.surface.answer(decision_id, choice)
        keep, dropped = self.speculation.resolve(d)
        for cid in d.blocked:
            cm = self.graph.get(cid)
            if cm.ambiguous:
                # The judgment call WAS the work. Answering it completes it;
                # sending it back to `pending` would only have it re-escalated
                # on the next tick, forever.
                cm.status = Status.DONE
                cm.evidence.passed = True
                cm.evidence.detail = f"decided: {choice}"
                cm.notes = choice
                cm.log(f"decided by {d.id}: {choice!r}")
                # A decision is how a judgment call gets its evidence: a person
                # said so. Without this fact the log cannot explain why the
                # commitment is done, and replay drifts.
                self.record(EventKind.VERIFIED, commitment_id=cm.id,
                            decision_id=d.id, actor=cm.reviewer or "human",
                            detail=f"decided: {choice}")
            elif cm.status is Status.ESCALATED:
                cm.status = Status.PENDING
                cm.log(f"unblocked by {d.id} = {choice!r}")
        self.record(EventKind.ANSWERED, decision_id=d.id, actor=d.blocked and "human",
                    choice=choice, unblocked=len(d.blocked))
        for b in dropped:
            for cid in b.commitments:
                self.cost.settle(cid, "discarded")
                self.record(EventKind.DISCARDED, commitment_id=cid,
                            decision_id=d.id, branch=b.id)
        spent = self.cost.for_decision(d.id)
        self.metrics.speculative_cost += spent
        self.emit(f"ANSWER {d.id} = {choice!r}: unblocked {len(d.blocked)}, "
                  f"kept {1 if keep else 0} branch, discarded {len(dropped)}, "
                  f"speculation cost ${spent:.4f}")
