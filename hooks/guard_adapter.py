#!/usr/bin/env python3
import json
import os
import signal
import sys
import time
import traceback

LOG = os.path.expanduser("~/.claude/guard-failopen.log")
MAX_LOG = 256 * 1024

def log(why, detail=""):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG:
            os.replace(LOG, LOG + ".1")
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"{stamp} {why}: {detail[:2000]}\n")
    except Exception:                                # noqa: BLE001
        pass

def fail_open(why, detail=""):
    log(why, detail)
    sys.exit(0)

def read_payload(on_raw=None):
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
        fail_open("payload was not JSON", raw[:200] if isinstance(raw, str) else "")
    if not isinstance(payload, dict):
        fail_open("payload was not an object", type(payload).__name__)
    return payload

def field(payload, *keys):
    node = payload
    for k in keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(k)
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return node
    return "" if node is None else str(node)

ANALYSIS_BUDGET = float(os.environ.get("GUARD_ANALYSIS_BUDGET", "3.0"))

class _OutOfTime(Exception):
    pass

def _ring(_signum, _frame):
    raise _OutOfTime()

def _timed(fn, *args):
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
        fail_open("recursion limit in rules", "deeply nested payload")
    except Exception:                                # noqa: BLE001
        fail_open("rules raised", traceback.format_exc(limit=4))
    if hit is None:
        return None
    try:
        reason, fix = hit
    except Exception:                                # noqa: BLE001
        fail_open("rules returned a malformed verdict", repr(hit)[:200])
    return reason, fix

def block(reason, fix):
    sys.stderr.write(f"BLOCKED: {reason}\n\nDo this instead: {fix}\n")
    sys.exit(2)

def load_rules():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import guard_rules
        return guard_rules
    except Exception:                                # noqa: BLE001
        fail_open("rules module failed to import", traceback.format_exc(limit=4))
