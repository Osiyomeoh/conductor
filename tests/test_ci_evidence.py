"""CI-as-evidence: the repo's own CI is the verdict, delivered by webhook.

A commitment whose evidence is CI stays pending after a worker's claim; only a
CI result over the webhook resolves it, and Conductor's own commit status is
never mistaken for the CI.
"""
from conductor.models import Commitment, Evidence, EvidenceKind, Status
from conductor.verification import VerificationRunner
from conductor.webhook import handle_event


class FakeConductor:
    def __init__(self, commits):
        self.graph = commits
        self.events = []

    def emit(self, m):
        self.events.append(m)


def _cm(branch="conductor/cm_1"):
    cm = Commitment.new("Fix the webhook", Evidence(EvidenceKind.CI, spec="ci/build"))
    cm.branch = branch
    return cm


def test_ci_evidence_stays_pending_until_ci_reports():
    cm = _cm()
    v = VerificationRunner(runner=None)     # CI never touches the local runner
    assert v.verify(cm) is False            # not 'done'
    assert cm.evidence.passed is None       # pending, not believed
    assert cm.status is Status.VERIFYING


def test_check_suite_success_and_failure():
    ok = _cm(); c = FakeConductor([ok])
    out = handle_event("check_suite",
                       {"action": "completed",
                        "check_suite": {"conclusion": "success", "head_branch": "conductor/cm_1"}}, c)
    assert out["result"] == "pass" and out["commitment"] == ok.id
    assert ok.status is Status.DONE and ok.evidence.passed is True

    bad = _cm(); c2 = FakeConductor([bad])
    handle_event("check_suite",
                 {"action": "completed",
                  "check_suite": {"conclusion": "failure", "head_branch": "conductor/cm_1"}}, c2)
    assert bad.status is Status.REJECTED and bad.evidence.passed is False


def test_own_status_ignored_external_ci_resolves():
    cm = _cm(); c = FakeConductor([cm])
    # Conductor's own commit status must not be mistaken for the CI verdict.
    r = handle_event("status",
                     {"context": "conductor/cm_1", "state": "success",
                      "branches": [{"name": "conductor/cm_1"}]}, c)
    assert r["event"] == "status.self" and cm.evidence.passed is None
    # A real external CI status resolves it.
    r2 = handle_event("status",
                      {"context": "ci/github-actions", "state": "success",
                       "branches": [{"name": "conductor/cm_1"}]}, c)
    assert r2["result"] == "pass" and cm.status is Status.DONE
