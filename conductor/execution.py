"""Real execution substrate: git worktrees, real commands, real merges.

Conductor's core guarantee is that nothing an agent produces reaches shared
state until its evidence passes. For that to be true rather than decorative,
the isolation has to be real:

  - each dispatched commitment gets its own git worktree on its own branch
  - the worker operates only inside that worktree
  - the evidence command runs with its working directory in that worktree
  - a pass merges the branch into the base; a failure removes the worktree and
    the work is discarded, never seen

This is what makes speculation safe. Three branches building competing answers
cannot touch each other or the base, so wasting two of them costs nothing but
compute.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


def _git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True, check=check)


@dataclass
class GitExecutor:
    """Manages real worktrees against a real repository. Worktrees live under
    .conductor/wt/<branch> and never outlive their commitment."""
    repo: str
    base: str = "main"

    def __post_init__(self):
        self.repo = os.path.abspath(self.repo)
        self.wt_root = os.path.join(self.repo, ".conductor", "wt")
        os.makedirs(self.wt_root, exist_ok=True)
        # Resolve the real base branch name (main vs master vs current).
        try:
            head = _git(self.repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
            if head:
                self.base = head
        except subprocess.CalledProcessError:
            pass

    def open(self, branch: str) -> str:
        """Create a fresh worktree for a branch off the base. Returns its path.
        Idempotent: a re-dispatch reuses a clean worktree."""
        path = os.path.join(self.wt_root, branch.replace("/", "_"))
        self.close(branch, path)
        _git(self.repo, "branch", "-f", branch, self.base)
        _git(self.repo, "worktree", "add", "--force", path, branch)
        return path

    def verify_in(self, branch: str, command: str, timeout: int = 300) -> tuple[bool, str]:
        """Run the evidence command inside the branch's worktree."""
        path = os.path.join(self.wt_root, branch.replace("/", "_"))
        if not os.path.isdir(path):
            return False, "worktree missing"
        try:
            p = subprocess.run(command, shell=True, cwd=path, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        if p.returncode == 0:
            return True, (p.stdout or "").strip()[-400:]
        return False, f"exit {p.returncode}: {((p.stderr or p.stdout) or '').strip()[-400:]}"

    def commit(self, branch: str, message: str) -> bool:
        """Commit whatever the worker produced in its worktree onto its branch.
        Called before verification so the branch reflects the work and a pass
        has a real commit to merge."""
        path = os.path.join(self.wt_root, branch.replace("/", "_"))
        if not os.path.isdir(path):
            return False
        _git(path, "add", "-A", check=False)
        # 'nothing to commit' returns 1 and is fine: the worker produced nothing.
        _git(path, "commit", "-q", "-m", message, check=False)
        return True

    def merge(self, branch: str) -> tuple[bool, str]:
        """Merge a verified branch into the base and tear down its worktree.
        A real merge, so the base advances only for work that passed."""
        path = os.path.join(self.wt_root, branch.replace("/", "_"))
        _git(self.repo, "worktree", "remove", "--force", path, check=False)
        r = _git(self.repo, "merge", "--no-ff", "-m", f"conductor: merge {branch}",
                 branch, check=False)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout).strip()[-300:]
        _git(self.repo, "branch", "-D", branch, check=False)
        return True, "merged"

    def revert(self, branch: str) -> tuple[bool, str]:
        """Undo a merged branch after its outcome regressed: revert the merge
        commit on the base, so reality is restored without rewriting history."""
        r = _git(self.repo, "log", "--grep", f"conductor: merge {branch}",
                 "--format=%H", "-n", "1", check=False)
        sha = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
        if not sha:
            return False, "no merge commit to revert"
        rv = _git(self.repo, "revert", "--no-edit", "-m", "1", sha, check=False)
        if rv.returncode != 0:
            return False, (rv.stderr or rv.stdout).strip()[-200:]
        return True, f"reverted merge {sha[:8]}"

    def discard(self, branch: str) -> None:
        """Throw away a branch and its worktree. A rejected or losing branch
        leaves no trace on the base."""
        self.close(branch)
        _git(self.repo, "branch", "-D", branch, check=False)

    def close(self, branch: str, path: str | None = None) -> None:
        path = path or os.path.join(self.wt_root, branch.replace("/", "_"))
        if os.path.isdir(path):
            _git(self.repo, "worktree", "remove", "--force", path, check=False)

    def base_log(self, n: int = 10) -> list[str]:
        r = _git(self.repo, "log", "--oneline", "-n", str(n), self.base, check=False)
        return [ln for ln in r.stdout.splitlines() if ln.strip()]


def init_repo(path: str) -> str:
    """Create a real git repo with a base commit. Used to stand Conductor up
    against a fresh workspace."""
    os.makedirs(path, exist_ok=True)
    _git(path, "init", "-q", check=False) if not os.path.isdir(os.path.join(path, ".git")) else None
    subprocess.run(["git", "-C", path, "init", "-q"], check=False)
    _git(path, "config", "user.email", "conductor@local", check=False)
    _git(path, "config", "user.name", "Conductor", check=False)
    readme = os.path.join(path, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w") as f:
            f.write("# workspace\n")
        _git(path, "add", "-A", check=False)
        _git(path, "commit", "-q", "-m", "base", check=False)
    return path
