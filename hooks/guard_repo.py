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

All three used to be written out once per question, five times. That is how
`reset_state()` came to exist at all, per its own history: the caller cleared
the caches by reaching into this module and the sixth was never on the list.
It is also how two of the five came to CACHE the budget-exhausted answer, which
froze it for the rest of the process. One helper, so the three properties are
stated once and cannot drift apart again.

Python 3.9, stdlib only.
"""
import os
import subprocess

_CACHES = {}
_GIT_CALLS = [0]

MAX_GIT_CALLS = 40


def _ask(topic, key, unknown, answer):
    """One cached, budgeted, fail-closed git question.

    `unknown` is returned WITHOUT being cached. Caching it would make a spent
    budget permanent for the rest of the process, and every `unknown` here is
    the conservative answer, so freezing it silently turns rules off.
    """
    cache = _CACHES.setdefault(topic, {})
    if key in cache:
        return cache[key]
    if _GIT_CALLS[0] >= MAX_GIT_CALLS:
        return unknown
    _GIT_CALLS[0] += 1
    cache[key] = answer()
    return cache[key]


def _git(cwd, *args):
    """git, or None if it errored, hung, or is not installed."""
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
    """Is `name` a real local branch in this repo?

    Without this a `git checkout <file>` was taken as a branch switch and its
    argument became a fictional, non-protected branch for the rest of the line.
    """
    # False means no override, so the branch rule stands.
    return _ask("branch-exists", (cwd, name), False,
                lambda: _ok(cwd, "rev-parse", "--verify", "--quiet",
                            "refs/heads/" + name))


def rebase_in_progress(cwd):
    """Is a rebase stopped mid-flight here?

    An interactive rebase parked on an `edit` step leaves HEAD detached, and
    `git commit --amend` there is the entire point of that step. /unstick walks
    users into exactly this state, so the detached-HEAD rule has to know.
    """
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
    """False only for a freshly initialised repo with no commits.

    Fails CLOSED on any error: a broken lookup must not unlock the virgin-repo
    carve-out, so an absent or failing git reads as "has commits".
    """
    def answer():
        r = _git(cwd, "rev-parse", "HEAD")
        return True if r is None else r.returncode == 0
    return _ask("commits", cwd, True, answer)


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

    One clear, not a list of caches to keep in step with the ones above.
    """
    _CACHES.clear()
    _GIT_CALLS[0] = 0
