"""The check-runner sandbox: where an arbitrary evidence command executes.

Docker arg construction and CodeBuild flow are tested without Docker or AWS by
injecting the exec/boto layer; the local runner runs a real command; and the
verification runner is shown to route through whichever backend it is given, so
a lie is still caught through the sandbox.
"""
import subprocess

from conductor.sandbox import (CodeBuildRunner, DockerRunner, LocalRunner,
                               runner_from_env)


def test_local_runner_passes_and_fails_on_real_commands(tmp_path):
    r = LocalRunner()
    ok, _ = r.run(str(tmp_path), "exit 0", timeout=10)
    assert ok is True
    bad, detail = r.run(str(tmp_path), "exit 3", timeout=10)
    assert bad is False and "exit 3" in detail


def test_docker_runner_isolates_the_command(tmp_path):
    """The container is removed, network-disabled, resource-capped, and mounts
    only the worktree. Verified by asserting the argv without running Docker."""
    seen = {}

    def fake_exec(args, capture_output, text, timeout):
        seen["args"] = args
        class P:  # noqa: D401
            returncode = 0; stdout = "ok"; stderr = ""
        return P()

    r = DockerRunner(image="python:3.12-slim", _exec=fake_exec)
    ok, _ = r.run(str(tmp_path), "python -c 'print(1)'", timeout=30)
    a = seen["args"]
    assert ok is True
    assert a[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "--memory" in a and "--pids-limit" in a          # resource caps
    assert f"{tmp_path}:/work" in a and "-w" in a            # only the worktree, mounted
    assert a[-3:] == ["sh", "-c", "python -c 'print(1)'"]    # the check itself
    assert "--network" in a and a[a.index("--network") + 1] == "none"   # no network


def test_docker_runner_reports_missing_docker():
    def boom(*a, **k):
        raise FileNotFoundError("docker")
    ok, detail = DockerRunner(_exec=boom).run(".", "true", timeout=5)
    assert ok is False and "docker not available" in detail


def test_codebuild_runner_uploads_starts_and_polls(tmp_path):
    (tmp_path / "slugify.py").write_text("def slugify(s): return s.lower()\n")
    events = {"put": None, "build": None, "polls": 0}

    class FakeS3:
        def put_object(self, Bucket, Key, Body):
            events["put"] = (Bucket, Key, len(Body))

    class FakeCB:
        def start_build(self, **kw):
            events["build"] = kw
            return {"build": {"id": "b:1"}}
        def batch_get_builds(self, ids):
            events["polls"] += 1
            status = "IN_PROGRESS" if events["polls"] < 2 else "SUCCEEDED"
            return {"builds": [{"buildStatus": status}]}

    r = CodeBuildRunner(project="conductor-checks", bucket="my-bucket",
                        client=FakeCB(), s3=FakeS3())
    ok, detail = r.run(str(tmp_path), "python -c 'import slugify'", timeout=6)
    assert ok is True and "succeeded" in detail
    assert events["put"][0] == "my-bucket" and events["put"][2] > 0      # zip uploaded
    bs = events["build"]["buildspecOverride"]
    assert "python -c 'import slugify'" in bs                            # command in buildspec
    assert events["build"]["sourceTypeOverride"] == "S3"


def test_codebuild_runner_reports_failure(tmp_path):
    class FakeS3:
        def put_object(self, **k): pass
    class FakeCB:
        def start_build(self, **kw): return {"build": {"id": "b:2"}}
        def batch_get_builds(self, ids): return {"builds": [{"buildStatus": "FAILED"}]}
    ok, detail = CodeBuildRunner("p", "b", client=FakeCB(), s3=FakeS3()).run(str(tmp_path), "false", timeout=6)
    assert ok is False and "failed" in detail


def test_runner_from_env_selects_backend(monkeypatch):
    monkeypatch.delenv("CONDUCTOR_SANDBOX", raising=False)
    assert isinstance(runner_from_env(), LocalRunner)
    monkeypatch.setenv("CONDUCTOR_SANDBOX", "docker")
    assert isinstance(runner_from_env(), DockerRunner)
    monkeypatch.setenv("CONDUCTOR_SANDBOX", "codebuild")   # missing project -> safe fallback
    assert isinstance(runner_from_env(), LocalRunner)
    monkeypatch.setenv("CONDUCTOR_CODEBUILD_PROJECT", "p")
    monkeypatch.setenv("CONDUCTOR_CODEBUILD_BUCKET", "b")
    assert isinstance(runner_from_env(), CodeBuildRunner)


def test_verifier_routes_through_the_sandbox(tmp_path):
    """The verification runner catches a failing check via whatever runner it is
    handed — here a fake that always fails, proving the routing."""
    from conductor.models import Commitment, Evidence, EvidenceKind
    from conductor.verification import VerificationRunner

    class AlwaysFail:
        def run(self, workdir, command, timeout):
            return False, "sandbox says no"

    v = VerificationRunner(workdir=str(tmp_path), runner=AlwaysFail())
    cm = Commitment.new("t", Evidence(EvidenceKind.COMMAND, spec="true"))
    assert v.verify(cm) is False
    assert cm.evidence.detail == "sandbox says no"
