"""The WATCHING lifecycle: done means the metric moved AND stayed moved.

An outcome commitment is only done once its metric has held the target for a few
checks; a done outcome that later regresses is reopened and rolled back.
"""


def _conductor_with_outcome(monkeypatch, spec="signup >= 0.4"):
    monkeypatch.setenv("CONDUCTOR_WORK_DIR", "/tmp/watch-work")
    from conductor.metrics import MemoryMetricSource
    from conductor.models import Commitment, Evidence, EvidenceKind, Status
    from conductor.world import build
    c = build(seed=7)
    src = MemoryMetricSource()
    c.verifier.metric_source = src
    cm = Commitment.new("Lift signup", Evidence(EvidenceKind.OUTCOME, spec=spec))
    cm.status = Status.VERIFYING
    c.graph.add(cm)
    return c, src, cm


def test_outcome_must_hold_before_done(monkeypatch):
    from conductor.models import Status
    c, src, cm = _conductor_with_outcome(monkeypatch)
    src.set("signup", 0.50)                 # target reached...
    c._watch_outcomes()
    assert cm.status is Status.WATCHING and cm.hold_streak == 1   # ...but watch it hold
    c._watch_outcomes()
    assert cm.status is Status.DONE and cm.hold_streak == 2       # held twice -> done


def test_streak_resets_if_metric_dips_during_watch(monkeypatch):
    from conductor.models import Status
    c, src, cm = _conductor_with_outcome(monkeypatch)
    src.set("signup", 0.50)
    c._watch_outcomes()                     # streak 1
    src.set("signup", 0.30)                 # dipped before confirming
    c._watch_outcomes()
    assert cm.status is Status.WATCHING and cm.hold_streak == 0   # not done, reset


def test_regression_after_done_reopens_and_rolls_back(monkeypatch):
    from conductor.models import Status
    c, src, cm = _conductor_with_outcome(monkeypatch)
    src.set("signup", 0.50)
    c._watch_outcomes(); c._watch_outcomes()          # -> DONE
    assert cm.status is Status.DONE
    src.set("signup", 0.20)                           # reality reversed
    c._watch_outcomes()
    assert cm.status is Status.REJECTED
    assert cm.evidence.passed is False and "regressed" in cm.evidence.detail
    assert any("rolled back" in e for e in c.events)  # rollback triggered


def test_git_executor_revert(tmp_path):
    """The executor really reverts a merge commit on the base branch."""
    import subprocess
    from conductor.execution import GitExecutor
    repo = str(tmp_path)
    for a in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", repo, *a], check=True)
    (tmp_path / "f.txt").write_text("base\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "base"], check=True)
    gx = GitExecutor(repo=repo)
    wt = gx.open("conductor/cm_1")
    (open(f"{wt}/f.txt", "w")).write("changed\n")
    gx.commit("conductor/cm_1", "work")
    ok, _ = gx.merge("conductor/cm_1")
    assert ok and (tmp_path / "f.txt").read_text() == "changed\n"
    ok2, detail = gx.revert("conductor/cm_1")
    assert ok2 and (tmp_path / "f.txt").read_text() == "base\n"   # reality restored
