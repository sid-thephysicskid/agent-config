#!/usr/bin/env python3
"""What git says about the repository, cached and budgeted.

The only code in the guard that runs a subprocess. Everything else here matches
text; this asks git questions that text cannot answer, such as which branch is
checked out right now, and those answers are what make the protected-branch
rule possible at all.

Three properties matter more than the answers:

  CACHED   one command can name the same repo many times, and each miss is a
           process spawn.
  BUDGETED MAX_GIT_CALLS bounds the spawns per hook invocation. Past it every
           lookup returns the unknown value, and unknown fails CLOSED for
           commit and push.
  FAIL CLOSED  a git that errors, hangs or is missing must not read as "no
           protected branch here".

`reset_state()` exists because the caller used to clear five of these caches by
reaching into this module's private names, and the sixth was never on the list.
State is reset by the module that owns it.

Python 3.9, stdlib only.
"""
import os
import re
import subprocess

_BRANCH_CACHE = {}

_REPO_CACHE = {}

_GIT_CALLS = [0]

MAX_GIT_CALLS = 40

def current_branch(cwd):
    if cwd in _BRANCH_CACHE:
        return _BRANCH_CACHE[cwd]
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return None          # unknown, and unknown fails CLOSED for commit/push
    _GIT_CALLS[0] += 1
    _BRANCH_CACHE[cwd] = _current_branch_uncached(cwd)
    return _BRANCH_CACHE[cwd]

def _current_branch_uncached(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=cwd, capture_output=True, text=True, timeout=2)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

_BRANCH_EXISTS_CACHE = {}

def is_branch(cwd, name):
    """Is `name` a real local branch in this repo?

    Without this a `git checkout <file>` was taken as a branch switch and its
    argument became a fictional, non-protected branch for the rest of the line.
    """
    key = (cwd, name)
    if key in _BRANCH_EXISTS_CACHE:
        return _BRANCH_EXISTS_CACHE[key]
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return False         # unknown, so no override, so the branch rule stands
    _GIT_CALLS[0] += 1
    try:
        r = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                            "refs/heads/" + name],
                           cwd=cwd, capture_output=True, text=True, timeout=2)
        ok = r.returncode == 0
    except Exception:
        ok = False
    _BRANCH_EXISTS_CACHE[key] = ok
    return ok

_REBASE_CACHE = {}

def rebase_in_progress(cwd):
    """Is a rebase stopped mid-flight here?

    An interactive rebase parked on an `edit` step leaves HEAD detached, and
    `git commit --amend` there is the entire point of that step. /unstick walks
    users into exactly this state, so the detached-HEAD rule has to know.
    """
    if cwd in _REBASE_CACHE:
        return _REBASE_CACHE[cwd]
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return False        # unknown, and unknown must not excuse a commit
    _GIT_CALLS[0] += 1
    _REBASE_CACHE[cwd] = _rebase_in_progress_uncached(cwd)
    return _REBASE_CACHE[cwd]

def _rebase_in_progress_uncached(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--git-path", "rebase-merge"],
                           cwd=cwd, capture_output=True, text=True, timeout=2)
        if r.returncode == 0 and os.path.exists(os.path.join(cwd, r.stdout.strip())):
            return True
        r = subprocess.run(["git", "rev-parse", "--git-path", "rebase-apply"],
                           cwd=cwd, capture_output=True, text=True, timeout=2)
        return r.returncode == 0 and os.path.exists(os.path.join(cwd, r.stdout.strip()))
    except Exception:
        return False

def is_git_repo(cwd):
    if cwd in _REPO_CACHE:
        return _REPO_CACHE[cwd]
    _REPO_CACHE[cwd] = _is_git_repo_uncached(cwd)
    return _REPO_CACHE[cwd]

def _is_git_repo_uncached(cwd):
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return True     # unknown, and "assume repo" keeps the branch rules on
    _GIT_CALLS[0] += 1
    try:
        r = subprocess.run(["git", "rev-parse", "--git-dir"],
                           cwd=cwd, capture_output=True, text=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False

_COMMITS_CACHE = {}

def has_commits(cwd):
    if cwd in _COMMITS_CACHE:
        return _COMMITS_CACHE[cwd]
    _COMMITS_CACHE[cwd] = _has_commits_uncached(cwd)
    return _COMMITS_CACHE[cwd]

def _has_commits_uncached(cwd):
    """False only for a freshly `git init`ed repo with no commits. Fails
    CLOSED (returns True) on any error, so a broken lookup cannot unlock the
    virgin-repo carve-out."""
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return True     # unknown, so NOT virgin, so the commit rule still applies
    _GIT_CALLS[0] += 1
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           cwd=cwd, capture_output=True, text=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return True

def is_virgin_repo(cwd):
    """A real repo that has no commits yet. `/bootstrap` needs its first commit
    on main to be allowed. A directory that is not a repo at all is NOT virgin:
    treating it as one made the whole rule depend on the process cwd."""
    return is_git_repo(cwd) and not has_commits(cwd)


def reset_state():
    """Forget everything learned about the filesystem, and refill the budget.

    Called once per outermost check_command. In production a hook process
    judges one command and exits, so this is invisible; in the suites, which
    run thousands of commands in one process against the same fixture paths, a
    stale answer would leak from case to case.
    """
    _BRANCH_CACHE.clear()
    _BRANCH_EXISTS_CACHE.clear()
    _REPO_CACHE.clear()
    _COMMITS_CACHE.clear()
    _REBASE_CACHE.clear()
    _GIT_CALLS[0] = 0
