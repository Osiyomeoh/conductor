"""Consequence signals: recognizing production / money / customer work.

The classifier reads a commitment and the policy engine blocks the dangerous
kinds, so a deploy or a refund is escalated to a human, never run by an agent.
"""
from conductor.models import Action, Decision
from conductor.policy import PolicyEngine
from conductor.signals import classify


class CM:
    def __init__(self, title, kind="code", consequential=False):
        self.title = title
        self.work_kind = kind
        self.artifact_path = ""
        self.consequential = consequential
        self.branch = None
        self.evidence = None


import pytest


@pytest.fixture(autouse=True)
def _signals_on(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_SIGNALS", "1")   # full detection for these tests


def test_signals_off_by_default_preserves_demo(monkeypatch):
    monkeypatch.delenv("CONDUCTOR_SIGNALS", raising=False)
    # A deploy-titled commitment is NOT flagged by keyword when signals are off.
    assert classify(CM("Deploy to production")) == {"touches_production": False}


def test_classify_detects_each_consequence():
    assert classify(CM("Deploy the service to production"))["touches_production"]
    assert classify(CM("Run the database migration"))["touches_production"]
    assert classify(CM("Process a customer refund"))["touches_money"]
    assert classify(CM("Email the customer about the outage"))["speaks_to_customer"]
    benign = classify(CM("Implement slugify(text)"))
    assert not any(benign.values())


def test_env_patterns_extend_detection(monkeypatch):
    monkeypatch.setenv("CONDUCTOR_PRODUCTION_PATTERNS", "helm chart, ansible")
    assert classify(CM("Update the helm chart"))["touches_production"]


def test_policy_blocks_production_and_money():
    for title in ("Deploy to production", "Process a refund for the customer"):
        action = Action(kind="dispatch", commitment_id="c", summary="x",
                        payload=classify(CM(title)))
        v = PolicyEngine(autonomy=1.0).evaluate(action)   # full autonomy still blocks
        assert v.decision is Decision.BLOCK

    ok = Action(kind="dispatch", commitment_id="c", summary="x",
                payload=classify(CM("Implement slugify(text)")))
    assert PolicyEngine(autonomy=0.6).evaluate(ok).decision is not Decision.BLOCK
