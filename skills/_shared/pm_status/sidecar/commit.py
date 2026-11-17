"""pm_status.sidecar.commit -- commit exactly the sidecar files a v7 hook wrote.

Every l3io hook on a v7 skill runs where the next `bmad-build-auto` will demand a clean tree
(`step-01-clarify-and-route.md:60`), so a hook that writes a tracked file commits it before it
returns. It commits the paths it was given and nothing else: `git commit -- <paths>` takes
only those, so a user's own staged or unstaged work is left exactly as it was.

A path outside the current worktree is skipped (in a linked worktree the project-wide state
root is the main checkout's), as is an ignored path. A path that no longer exists is
committed as a deletion when git tracks it, which is how a sidecar `sidecar-reconcile`
moved leaves its old place. Outside git there is nothing to do.
"""
from __future__ import annotations

import os
import subprocess


def _git(cwd: str, *argv) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *argv], capture_output=True, text=True,
                          check=False)


def toplevel(path: str):
    """The worktree `path` is in, or None outside git."""
    try:
        r = _git(path, "rev-parse", "--show-toplevel")
    except OSError:
        return None
    return os.path.realpath(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def commit_paths(project_root: str, paths: list, message: str) -> str:
    """Commit each of `paths` inside the current worktree, and nothing else. Returns an error
    message, or "" (including when there was nothing to commit)."""
    top = toplevel(project_root)
    if top is None:
        return ""
    inside = []
    for p in dict.fromkeys(paths):
        real = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
        if not real.startswith(top + os.sep):
            continue
        rel = os.path.relpath(real, top)
        if not os.path.exists(real):
            if _git(top, "ls-files", "--error-unmatch", "--", rel).returncode == 0:
                inside.append(rel)
            continue
        if _git(top, "check-ignore", "-q", "--", rel).returncode == 0:
            continue
        inside.append(rel)
    if not inside:
        return ""
    r = _git(top, "add", "-A", "--", *inside)
    if r.returncode == 0 and _git(top, "status", "--porcelain", "--", *inside).stdout.strip():
        r = _git(top, "commit", "-q", "-m", message, "--", *inside)
    return "" if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip())
