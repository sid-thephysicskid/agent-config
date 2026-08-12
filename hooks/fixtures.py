#!/usr/bin/env python3
"""Throwaway git repos every guard case is judged against.

Separate module so both suites and any ad-hoc script can build the same
world without copying the setup and drifting from it.
"""
import atexit
import os
import shutil
import subprocess
import tempfile

HOME = os.path.expanduser("~")

def mkrepo(branch, commit=True):
    d = tempfile.mkdtemp()
    q = dict(cwd=d, capture_output=True, text=True)
    subprocess.run(["git", "init", "-q"], **q)
    subprocess.run(["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"], **q)
    if commit:
        subprocess.run(["git", "config", "user.email", "t@t.t"], **q)
        subprocess.run(["git", "config", "user.name", "t"], **q)
        open(os.path.join(d, "f"), "w").write("x")
        subprocess.run(["git", "add", "f"], **q)
        subprocess.run(["git", "commit", "-qm", "init"], **q)
        # A second REAL branch, so `git checkout feature/y -- f` exercises the
        # is_branch lookup instead of failing it. Without one, the checkout
        # tests passed because the name did not resolve, not because the
        # `--` rule fired, and the rule was deletable with the suite green.
        subprocess.run(["git", "branch", "feature/y"], **q)
    return d


def mkdetached():
    """A repo sitting on a detached HEAD, which is where `git bisect run` and
    an interactive rebase leave you. `branch --show-current` prints nothing and
    `rev-parse --abbrev-ref` answers the literal string HEAD."""
    d = mkrepo("main")
    q = dict(cwd=d, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-qm", "second", "--allow-empty"], **q)
    sha = subprocess.run(["git", "rev-parse", "HEAD~1"], **q).stdout.strip()
    subprocess.run(["git", "checkout", "-q", sha], **q)
    return d


NOREPO = tempfile.mkdtemp()          # a real directory that is NOT a repo
MAIN = mkrepo("main")
FEAT = mkrepo("feature/x")
VIRGIN = mkrepo("main", commit=False)
DETACHED = mkdetached()

# The fixtures are temp git repos; clean them up so repeated runs (install.sh
# runs this suite every time) do not litter the temp directory.
atexit.register(lambda: [shutil.rmtree(d, ignore_errors=True)
                         for d in (MAIN, FEAT, VIRGIN, NOREPO, DETACHED)])
