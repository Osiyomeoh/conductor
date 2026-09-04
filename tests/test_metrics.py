"""Outcome verification: done means the metric moved, not that code merged.

The core 1000x primitive. An outcome is verified only when a real metric hits its
target; an unmet target is pending (the work may be right and the metric simply
hasn't moved), never a rejection.
"""
from conductor.metrics import MemoryMetricSource, evaluate, parse_outcome
from conductor.models import Commitment, Evidence, EvidenceKind, Status
from conductor.verification import VerificationRunner


def test_parse_outcome():
    assert parse_outcome("signup_completion >= 0.4") == ("signup_completion", ">=", 0.4)
    assert parse_outcome("p99 < 200") == ("p99", "<", 200.0)
    assert parse_outcome("nonsense") is None
    assert parse_outcome("") is None


def test_evaluate_met_unmet_missing_malformed():
    src = MemoryMetricSource()
    src.set("signup", 0.5)
    assert evaluate("signup >= 0.4", src)[0] is True          # met
    assert evaluate("signup >= 0.9", src)[0] is None          # not reached yet (pending, not fail)
    assert evaluate("other >= 1", src)[0] is None             # not reported yet
    assert evaluate("garbage", src)[0] is False               # malformed is a planning defect
    assert evaluate("x >= 1", None)[0] is None                # no source -> pending


def _cm():
    return Commitment.new("Lift onboarding completion",
                          Evidence(EvidenceKind.OUTCOME, spec="onboarding >= 0.40"))


def test_outcome_verification_done_only_when_metric_hits_target():
    src = MemoryMetricSource()
    v = VerificationRunner(metric_source=src)

    cm = _cm()
    src.set("onboarding", 0.30)                # below target
    assert v.verify(cm) is False               # not done
    assert cm.evidence.passed is None and cm.status is Status.VERIFYING   # watched, not rejected

    src.set("onboarding", 0.42)                # target reached
    assert v.verify(cm) is True                # now done: reality changed
    assert cm.status is Status.DONE


def test_outcome_pending_without_a_metric_source():
    cm = _cm()
    v = VerificationRunner(metric_source=None)
    assert v.verify(cm) is False
    assert cm.status is Status.VERIFYING       # no source -> can't confirm reality yet
