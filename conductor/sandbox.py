"""Where a check actually runs.

A commitment's evidence is an arbitrary command, and once Conductor works on
repos it does not own, running that command in-process on the server is remote
code execution waiting to happen. This module makes the execution site pluggable:

  local       run on the host (fine for a trusted local machine and the demo)
  docker      run in an ephemeral, network-isolated container with resource caps
  codebuild   run in AWS CodeBuild, one disposable build per check (cloud scale)

All three satisfy one interface: run(workdir, command, timeout) -> (passed, detail).
The verification runner calls that and never a subprocess directly, so hardening
the sandbox is a one-line env change, not a code change. Selected by
CONDUCTOR_SANDBOX (default: local).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


def _result(returncode: int, out: str, err: str) -> tuple[bool, str]:
    if returncode == 0:
        return True, (out or "").strip()[-400:]
    return False, f"exit {returncode}: {((err or out) or '').strip()[-400:]}"


@dataclass
class LocalRunner:
    """Run the check on the host. No isolation: only for a trusted machine."""
    def run(self, workdir: str, command: str, timeout: int) -> tuple[bool, str]:
        try:
            p = subprocess.run(command, shell=True, cwd=workdir, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        return _result(p.returncode, p.stdout, p.stderr)


@dataclass
class DockerRunner:
    """Run the check inside a throwaway container: no network, capped memory,
    CPU and processes, the worktree mounted at /work, removed on exit. A hostile
    check can neither reach the network nor touch anything but its own worktree.
    `image` should carry the tools the checks need (default suits Python)."""
    image: str = "python:3.12-slim"
    memory: str = "512m"
    cpus: str = "1"
    pids: str = "256"
    _exec: object = None      # injectable for tests; defaults to subprocess.run

    def args(self, workdir: str, command: str) -> list[str]:
        return ["docker", "run", "--rm", "--network", "none",
                "--memory", self.memory, "--cpus", self.cpus, "--pids-limit", self.pids,
                "-v", f"{os.path.abspath(workdir)}:/work", "-w", "/work",
                self.image, "sh", "-c", command]

    def run(self, workdir: str, command: str, timeout: int) -> tuple[bool, str]:
        runner = self._exec or subprocess.run
        try:
            p = runner(self.args(workdir, command), capture_output=True, text=True,
                       timeout=timeout + 15)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        except FileNotFoundError:
            return False, "docker not available on this host"
        return _result(p.returncode, p.stdout, p.stderr)


@dataclass
class CodeBuildRunner:
    """Run the check in AWS CodeBuild: one disposable build per check, isolated
    by AWS. The worktree is zipped to S3, a build runs the command, and its exit
    status is the verdict. `client` (a boto3 codebuild client) and `s3` are
    injectable so the flow is tested without AWS."""
    project: str
    bucket: str
    region: str = "us-west-2"
    client: object = None
    s3: object = None

    def _clients(self):
        import boto3
        s = boto3.Session(region_name=self.region)
        return (self.client or s.client("codebuild"), self.s3 or s.client("s3"))

    def run(self, workdir: str, command: str, timeout: int) -> tuple[bool, str]:
        import io
        import time
        import zipfile
        cb, s3 = self._clients()

        # Zip the worktree and upload it as this build's source.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _dirs, files in os.walk(workdir):
                if ".git" in root:
                    continue
                for f in files:
                    full = os.path.join(root, f)
                    z.write(full, os.path.relpath(full, workdir))
        key = f"checks/{int(time.time()*1000)}.zip"
        s3.put_object(Bucket=self.bucket, Key=key, Body=buf.getvalue())

        started = cb.start_build(
            projectName=self.project,
            sourceTypeOverride="S3",
            sourceLocationOverride=f"{self.bucket}/{key}",
            buildspecOverride=(
                "version: 0.2\nphases:\n  build:\n    commands:\n"
                f"      - {command}\n"),
            timeoutInMinutesOverride=max(1, timeout // 60 + 1))
        build_id = started["build"]["id"]

        deadline = time.time() + timeout + 60
        while time.time() < deadline:
            b = cb.batch_get_builds(ids=[build_id])["builds"][0]
            if b.get("buildStatus") not in (None, "IN_PROGRESS"):
                ok = b["buildStatus"] == "SUCCEEDED"
                return ok, f"codebuild {b['buildStatus'].lower()}"
            time.sleep(3)
        return False, f"codebuild timed out after {timeout}s"


def runner_from_env():
    """Pick the check runner from CONDUCTOR_SANDBOX. Falls back to local so the
    demo and a trusted machine keep working with zero configuration."""
    mode = os.environ.get("CONDUCTOR_SANDBOX", "local").lower()
    if mode == "docker":
        return DockerRunner(image=os.environ.get("CONDUCTOR_SANDBOX_IMAGE", "python:3.12-slim"))
    if mode == "codebuild":
        project = os.environ.get("CONDUCTOR_CODEBUILD_PROJECT")
        bucket = os.environ.get("CONDUCTOR_CODEBUILD_BUCKET")
        if project and bucket:
            return CodeBuildRunner(project=project, bucket=bucket,
                                   region=os.environ.get("CONDUCTOR_REGION", "us-west-2"))
    return LocalRunner()
