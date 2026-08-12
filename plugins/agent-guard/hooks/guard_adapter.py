#!/usr/bin/env python3
"""Shared plumbing for the three host adapters.

Fail-open is the design: a bug in a guard must never brick the agent. The
problem was never the policy, it was that fail-open had NO SIGNAL. Exit 0 and a
crash were indistinguishable to the host, nothing was written anywhere, and the
adapter suite asserted only `returncode == 2`. A refactor that broke an import
would ship green with the guard silently off.

So: every fail-open path routed through here still exits 0, and every one of
them records why. If the guard ever goes quiet, `~/.claude/guard-failopen.log`
says when it started and what the input was.

guard-codex.py accepts a few legacy field names in addition to Codex's public
payload, but its parsing and every fail-open path still run through this module.
"""
import json
import os
import signal
import sys
import time
import traceback

LOG = os.path.expanduser("~/.claude/guard-failopen.log")
MAX_LOG = 256 * 1024


def log(why, detail=""):
    """Leave a trace. Never raises: a logging failure must change no verdict."""
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG:
            os.replace(LOG, LOG + ".1")
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        # 0600, for the reason guard-codex.py states about its own log: a
        # payload can carry a token or a file body, and this lands in a
        # long-lived file. That file is opt-in and this one is always on, so
        # the argument is strictly stronger here. It was 0644.
        fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"{stamp} {why}: {detail[:2000]}\n")
    except Exception:                                # noqa: BLE001
        pass


def fail_open(why, detail=""):
    """Allow the command, and leave a trace that we did so blindly.

    Split from `log` so a fail-closed path can record itself without also
    allowing. Every caller here still exits 0: a bug in a guard must not brick
    the agent, which is the trade the whole design is built on.
    """
    log(why, detail)
    sys.exit(0)


def read_payload(on_raw=None):
    """Parse the hook payload, or fail open with a reason.

    `on_raw` is handed the undecoded text before parsing, for the Codex
    adapter's opt-in payload log: it has to record what actually arrived,
    including something this function is about to reject.
    """
    # Read BYTES and decode leniently. A host can hand over a payload that is
    # not valid UTF-8, and `sys.stdin.read()` raised on it, which turned a
    # perfectly judgeable `rm -rf /` into a silent allow. A replacement
    # character in an argument cannot hide a destructive verb.
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    except Exception as e:                           # noqa: BLE001
        fail_open("stdin unreadable", repr(e))
    if on_raw is not None:
        try:
            on_raw(raw)
        except Exception:                            # noqa: BLE001
            pass          # a logging failure must never change the verdict
    try:
        payload = json.loads(raw)
    except Exception:
        # Not JSON is normal enough (a host probing the hook) that it is not
        # worth logging a stack trace, but it IS worth knowing it happened.
        fail_open("payload was not JSON", raw[:200] if isinstance(raw, str) else "")
    if not isinstance(payload, dict):
        fail_open("payload was not an object", type(payload).__name__)
    return payload


def field(payload, *keys):
    """payload[k1][k2]... as a string, or "" if any hop is the wrong shape.

    `tool_input` arriving as a string or a list used to raise AttributeError
    OUTSIDE the try, so the adapter exited 1 with a traceback rather than
    failing open deliberately.
    """
    node = payload
    for k in keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(k)
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        # A list of paths: judge them ALL. Taking element [0] meant
        # ["/safe/a.txt", "/app/.env"] was allowed and the reverse blocked.
        return node
    return "" if node is None else str(node)


# The host kills a hook at 5s and reads the kill as "allowed". So the slowest
# path in the rules is also the widest hole in them: an attacker who cannot
# find a spelling the parser misses can instead find one it is slow on, and
# every evasion rule in this repo is capped by that.
#
# This budget is deliberately under the host's. When it expires we still answer
# in time, and we answer from MIDDLE_SIGNALS: the loose, linear, no-backtracking
# list each rule module publishes for text it cannot parse. If that list sees
# something, we BLOCK. Slow input stops being a way through.
ANALYSIS_BUDGET = float(os.environ.get("GUARD_ANALYSIS_BUDGET", "3.0"))
# The rule modules' MIDDLE_SIGNALS tuples and the parser's DoS budgets are
# what keep ordinary large commands far under this. Measured 2026-08-08: a
# 270KB heredoc write lands 30x under, 400 small heredocs 38x under. They
# look like anti-evasion leftovers and they are not; without them a real
# file write would cross the budget and be refused.



class _OutOfTime(Exception):
    pass


def _ring(_signum, _frame):
    raise _OutOfTime()


def _timed(fn, *args):
    """Run `fn`, or raise _OutOfTime once the budget is gone.

    SIGALRM, because this is a short-lived single-threaded CLI and a thread
    would need the rules to be interruptible, which regexes are not. Where the
    signal is unavailable the call runs untimed and the old fail-open
    behaviour stands, which is no worse than before.
    """
    if not hasattr(signal, "SIGALRM"):
        return fn(*args)
    old = signal.signal(signal.SIGALRM, _ring)
    signal.setitimer(signal.ITIMER_REAL, ANALYSIS_BUDGET)
    try:
        return fn(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def verdict(fn, *args):
    """Run a rules function, fail open with a reason if it misbehaves.

    Except on timeout, where it fails CLOSED if the cheap scan sees anything.
    """
    try:
        hit = _timed(fn, *args)
    except _OutOfTime:
        rules = sys.modules.get("guard_rules")
        text = " ".join(str(a) for a in args if isinstance(a, str))
        if rules is not None and rules.MIDDLE_SIGNALS.search(text):
            log("analysis timed out on a command the cheap scan flagged",
                text[:200])
            return ("a command this guard could not finish analysing in %gs, "
                    "which also matches one of its destructive shapes."
                    % ANALYSIS_BUDGET,
                    "run the parts separately, so each one can be judged on its own")
        fail_open("analysis timed out, cheap scan saw nothing", text[:200])
    except RecursionError:
        # A deeply nested payload exhausts the stack inside the rules. Real,
        # measured at roughly 992 levels, and it used to allow silently.
        fail_open("recursion limit in rules", "deeply nested payload")
    except Exception:                                # noqa: BLE001
        fail_open("rules raised", traceback.format_exc(limit=4))
    if hit is None:
        return None
    try:
        reason, fix = hit
    except Exception:                                # noqa: BLE001
        # A malformed return is a guard bug. Blocking on it would be worse
        # than allowing, but it must not be silent.
        fail_open("rules returned a malformed verdict", repr(hit)[:200])
    return reason, fix


def block(reason, fix):
    sys.stderr.write(f"BLOCKED: {reason}\n\nDo this instead: {fix}\n")
    sys.exit(2)


def load_rules():
    """Import the rule modules, or fail open with a reason.

    The import used to sit at module scope outside every try, so a missing or
    broken rules module exited 1 with a traceback. The host treats that as
    "not blocked", which is fail-open by accident rather than by design.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import guard_rules
        return guard_rules
    except Exception:                                # noqa: BLE001
        fail_open("rules module failed to import", traceback.format_exc(limit=4))
