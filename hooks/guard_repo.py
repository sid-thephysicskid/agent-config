#!/usr/bin/env python3
import os
import subprocess

_CACHES = {}
_GIT_CALLS = [0]

MAX_GIT_CALLS = 40

def _ask(topic, key, unknown, answer):
    cache = _CACHES.setdefault(topic, {})
    if key in cache:
        return cache[key]
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return unknown
    _GIT_CALLS[0] += 1
    cache[key] = answer()
    return cache[key]

def _git(cwd, *args):
    try:
        return subprocess.run(["git", *args], cwd=cwd,
                              capture_output=True, text=True, timeout=2)
    except Exception:
        return None

def _ok(cwd, *args):
    r = _git(cwd, *args)
    return bool(r and r.returncode == 0)

def current_branch(cwd):
    def answer():
        r = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
        return r.stdout.strip() if r and r.returncode == 0 else None
    # None is unknown, and unknown fails CLOSED for commit and push.
    return _ask("branch", cwd, None, answer)

def is_branch(cwd, name):
    # False means no override, so the branch rule stands.
    return _ask("branch-exists", (cwd, name), False,
                lambda: _ok(cwd, "rev-parse", "--verify", "--quiet",
                            "refs/heads/" + name))

def rebase_in_progress(cwd):
    def answer():
        for path in ("rebase-merge", "rebase-apply"):
            r = _git(cwd, "rev-parse", "--git-path", path)
            if r and r.returncode == 0 \
                    and os.path.exists(os.path.join(cwd, r.stdout.strip())):
                return True
        return False
    # False, because unknown must not excuse a commit.
    return _ask("rebase", cwd, False, answer)

def is_git_repo(cwd):
    # True, because "assume repo" keeps the branch rules on.
    return _ask("repo", cwd, True, lambda: _ok(cwd, "rev-parse", "--git-dir"))

def has_commits(cwd):
    def answer():
        r = _git(cwd, "rev-parse", "HEAD")
        return True if r is None else r.returncode == 0
    return _ask("commits", cwd, True, answer)

def is_virgin_repo(cwd):
    return is_git_repo(cwd) and not has_commits(cwd)

def reset_state():
    _CACHES.clear()
    _GIT_CALLS[0] = 0
