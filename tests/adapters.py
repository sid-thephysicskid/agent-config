#!/usr/bin/env python3
"""The adapters, fed everything a host might actually hand them.

Run: python3 tests/adapters.py

This layer had five boolean assertions for ~200 lines across three hosts, and
a defect here silently disables everything behind it. Every row below is an
input that used to crash (exit 1, which the host reads as "allowed") or
silently allow with no trace.

Every row is an input that used to crash (exit 1) or silently allow with no
trace. The contract now: exit 2 to block, exit 0 to allow, never anything else,
and every blind allow leaves a line in the fail-open log.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile

H = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
BASH = os.path.join(H, "guard-bash.py")
FILES = os.path.join(H, "guard-files.py")
CODEX = os.path.join(H, "guard-codex.py")
TEST_HOME = tempfile.TemporaryDirectory()
LOG = os.path.join(TEST_HOME.name, ".claude", "guard-failopen.log")

BAD = "rm -rf /"
SECRET = "/app/.env"


def run(adapter, payload, raw=None):
    """Feed BYTES, not text: a host can hand over a payload that is not valid
    UTF-8, and encoding it in the test would hide what the adapter must survive."""
    data = raw if raw is not None else json.dumps(payload)
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogateescape")
    p = subprocess.run(["python3", adapter], input=data, capture_output=True,
                       env=dict(os.environ, HOME=TEST_HOME.name))
    return p.returncode, p.stderr.decode("utf-8", "replace")


def deep_raw(n):
    """A payload nested n levels, as TEXT.

    Built as a string because json.dumps hits Python's own recursion limit
    building it, which is itself a hint at what the adapter was facing.
    """
    return ('{"tool_name":"Bash","tool_input":{"command":"' + BAD + '"},"junk":'
            + '{"x":' * n + '1' + '}' * n + '}')


CASES = [
    # (label, adapter, payload, raw, expected exit)
    # These three came from a second, smaller adapter check that lived in
    # hooks/tests.py and spawned its own subprocesses. Everything else it
    # covered was already here.
    ("argv-form command blocks", BASH, {"tool_name": "Bash",
                                        "tool_input": {"command": ["rm", "-rf", "/"]}}, None, 2),
    ("codex shell tool blocks", CODEX, {"tool_name": "shell",
                                       "tool_input": {"command": BAD}}, None, 2),
    ("empty tool_input fails open", BASH, {"tool_name": "Bash",
                                           "tool_input": {}}, None, 0),
    ("baseline block", BASH, {"tool_name": "Bash",
                              "tool_input": {"command": BAD}}, None, 2),
    ("baseline allow", BASH, {"tool_name": "Bash",
                              "tool_input": {"command": "npm test"}}, None, 0),
    ("tool_input is a string", BASH, {"tool_name": "Bash",
                                      "tool_input": "oops"}, None, 0),
    ("tool_input is a list", BASH, {"tool_name": "Bash",
                                    "tool_input": ["oops"]}, None, 0),
    ("tool_input is null", BASH, {"tool_name": "Bash", "tool_input": None}, None, 0),
    # An unresolvable cwd fails CLOSED for a destructive command, which is
    # stronger than fail-open and the right call: we cannot tell what it would
    # have deleted.
    ("cwd is a dict", BASH, {"tool_name": "Bash", "tool_input": {"command": BAD},
                             "cwd": {"a": 1}}, None, 2),
    ("cwd is a list", BASH, {"tool_name": "Bash", "tool_input": {"command": BAD},
                             "cwd": ["/tmp"]}, None, 2),
    ("tool_name is null", BASH, {"tool_name": None,
                                 "tool_input": {"command": BAD}}, None, 0),
    ("tool_name is a dict", BASH, {"tool_name": {},
                                   "tool_input": {"command": BAD}}, None, 0),
    ("lowercase tool name", BASH, {"tool_name": "bash",
                                   "tool_input": {"command": BAD}}, None, 2),
    # Version-dependent, deliberately. On Python 3.9 this exhausts the stack
    # inside the rules and the adapter fails open WITH A LOG LINE; on 3.13 the
    # rules survive it and block. Both are acceptable; exit 1, or a silent
    # allow, are not. `None` here means "either, but it must not crash".
    ("deep nesting (1200)", BASH, None, deep_raw(1200), None),
    ("not JSON", BASH, None, "this is not json", 0),
    ("empty stdin", BASH, None, "", 0),
    ("JSON array", BASH, None, "[1,2,3]", 0),
    ("JSON string", BASH, None, '"hello"', 0),
    ("non-UTF8 bytes", BASH, None, '{"tool_name":"Bash","tool_input":'
                                   '{"command":"rm -rf /\udcff"}}', 2),

    ("file: block a secret read", FILES, {"tool_name": "Read",
                                          "tool_input": {"file_path": SECRET}}, None, 2),
    ("file: allow a source read", FILES, {"tool_name": "Read",
                                          "tool_input": {"file_path": "/a/x.ts"}}, None, 0),
    ("file: secret at index 1 of a list", FILES,
     {"tool_name": "Read", "tool_input": {"file_path": ["/safe/a.txt", SECRET]}}, None, 2),
    ("file: secret at index 0 of a list", FILES,
     {"tool_name": "Read", "tool_input": {"file_path": [SECRET, "/safe/a.txt"]}}, None, 2),
    ("file: `path` key instead", FILES,
     {"tool_name": "Write", "tool_input": {"path": SECRET}}, None, 2),
    ("file: `target_file` key", FILES,
     {"tool_name": "Write", "tool_input": {"target_file": SECRET}}, None, 2),
    ("file: renamed tool Update", FILES,
     {"tool_name": "Update", "tool_input": {"file_path": SECRET}}, None, 2),
    ("file: renamed tool StrReplace", FILES,
     {"tool_name": "StrReplace", "tool_input": {"file_path": SECRET}}, None, 2),
    ("file: MCP secret read", FILES,
     {"tool_name": "mcp__filesystem__read_file",
      "tool_input": {"path": SECRET}}, None, 2),
    ("file: MCP guard write", FILES,
     {"tool_name": "mcp__filesystem__write_file",
      "tool_input": {"path": "/home/me/.claude/settings.json"}}, None, 2),
    ("file: MCP move checks destination", FILES,
     {"tool_name": "mcp__filesystem__move_file",
      "tool_input": {"source": "/app/src/a.py", "destination": SECRET}}, None, 2),
    ("file: MCP multiple read checks every path", FILES,
     {"tool_name": "mcp__filesystem__read_multiple_files",
      "tool_input": {"paths": ["/app/src/a.py", SECRET]}}, None, 2),
    ("file: MCP source read is allowed", FILES,
     {"tool_name": "mcp__filesystem__read_text_file",
      "tool_input": {"path": "/app/src/a.py"}}, None, 0),
    ("file: tool_input is a string", FILES,
     {"tool_name": "Read", "tool_input": "oops"}, None, 0),
    ("file: read-safe path is allowed", FILES,
     {"tool_name": "Read",
      "tool_input": {"file_path": os.path.expanduser("~/.ssh/config")}}, None, 0),
    ("file: writing it is blocked", FILES,
     {"tool_name": "Write",
      "tool_input": {"file_path": os.path.expanduser("~/.ssh/config")}}, None, 2),

    ("codex patch: block a secret update", CODEX,
     {"tool_name": "apply_patch", "tool_input":
      "*** Begin Patch\n*** Update File: /app/.env\n@@\n-old\n+new\n*** End Patch"},
     None, 2),
    ("codex patch: allow a source update", CODEX,
     {"tool_name": "apply_patch", "tool_input":
      "*** Begin Patch\n*** Update File: /app/src/a.py\n@@\n-old\n+new\n*** End Patch"},
     None, 0),
    ("codex patch: inspect every file", CODEX,
     {"tool_name": "apply_patch", "tool_input":
      "*** Begin Patch\n*** Update File: /app/src/a.py\n@@\n-a\n+b\n"
      "*** Update File: /app/.env\n@@\n-a\n+b\n*** End Patch"},
     None, 2),
    ("codex patch: block a guard mutation", CODEX,
     {"tool_name": "apply_patch", "tool_input":
      "*** Begin Patch\n*** Update File: /home/me/.codex/hooks.json\n@@\n-a\n+b\n*** End Patch"},
     None, 2),
    ("codex patch: inspect move destinations", CODEX,
     {"tool_name": "apply_patch", "tool_input":
      "*** Begin Patch\n*** Update File: /app/src/a.py\n*** Move to: /app/.env\n*** End Patch"},
     None, 2),
    ("codex MCP guard read is allowed", CODEX,
     {"tool_name": "mcp__filesystem__read_file",
      "tool_input": {"path": os.path.expanduser("~/.claude/hooks/guard-bash.py")}},
     None, 0),
    ("codex MCP guard write is blocked", CODEX,
     {"tool_name": "mcp__filesystem__write_file",
      "tool_input": {"path": os.path.expanduser("~/.claude/hooks/guard-bash.py")}},
     None, 2),
    ("codex MCP multiple read checks every path", CODEX,
     {"tool_name": "mcp__filesystem__read_multiple_files",
      "tool_input": {"paths": ["/app/src/a.py", SECRET]}}, None, 2),
    ("codex MCP move checks destination", CODEX,
     {"tool_name": "mcp__filesystem__move_file",
      "tool_input": {"source": "/app/src/a.py", "destination": SECRET}}, None, 2),
]

# The host kills a hook at 5s and reads the kill as "allowed", so the slowest
# path in the rules was also the widest hole in them: an attacker who cannot
# find a spelling the parser misses can look for one it is slow on instead.
#
# A budget of 1ms makes EVERY command time out, so these two exercise the
# timeout path rather than the rules. The destructive one must still be
# refused, from the cheap linear scan; the ordinary one must still be allowed,
# because a guard that blocks everything under load is a guard people remove.
SLOW_CASES = [
    ("timeout: destructive still refused", BASH,
     {"tool_name": "Bash", "tool_input": {"command": BAD}}, 2),
    ("timeout: ordinary still allowed", BASH,
     {"tool_name": "Bash", "tool_input": {"command": "npm test"}}, 0),
]

before = os.path.getsize(LOG) if os.path.exists(LOG) else 0
bad = []
for label, adapter, payload, want in SLOW_CASES:
    p = subprocess.run(["python3", adapter],
                       input=json.dumps(payload).encode(),
                       capture_output=True,
                       env=dict(os.environ, HOME=TEST_HOME.name,
                                GUARD_ANALYSIS_BUDGET="0.001"))
    if p.returncode != want:
        bad.append((label, want, p.returncode,
                    p.stderr.decode("utf-8", "replace").strip().splitlines()[:1]))
for label, adapter, payload, raw, want in CASES:
    rc, err = run(adapter, payload, raw)
    if rc not in (0, 2):
        # The contract, above everything else: block or allow, never crash.
        # An exit code outside {0, 2} is read by the host as "not blocked",
        # which is fail-open by accident rather than by design.
        bad.append((label, want, rc, ["exit code outside the contract {0, 2}"]))
    elif want is not None and rc != want:
        bad.append((label, want, rc, err.strip().splitlines()[:1]))

# Repair the permissions of an existing log too. Passing 0600 to O_CREAT only
# affects a new file, so an old 0644 log otherwise stays readable by others.
with tempfile.TemporaryDirectory() as home:
    log_dir = os.path.join(home, ".claude")
    os.mkdir(log_dir)
    private_log = os.path.join(log_dir, "guard-failopen.log")
    with open(private_log, "w") as fh:
        fh.write("old\n")
    os.chmod(private_log, 0o644)
    subprocess.run(["python3", BASH], input=b"not json", capture_output=True,
                   env=dict(os.environ, HOME=home))
    mode = stat.S_IMODE(os.stat(private_log).st_mode)
    if mode != 0o600:
        bad.append(("existing fail-open log becomes private", "0600",
                    oct(mode), []))

_total = len(CASES) + len(SLOW_CASES) + 1
print(f"ADAPTER MATRIX: {_total - len(bad)}/{_total} correct")
for label, want, got, err in bad:
    print(f"  WRONG  {label}: wanted exit {want}, got {got} {err}")

after = os.path.getsize(LOG) if os.path.exists(LOG) else 0
print(f"\nfail-open log grew by {after - before} bytes "
      f"({'silent' if after == before else 'recorded'})")
if os.path.exists(LOG):
    with open(LOG) as fh:
        tail = fh.readlines()[-4:]
    for line in tail:
        print("   ", line.rstrip()[:110])
sys.exit(1 if bad else 0)
