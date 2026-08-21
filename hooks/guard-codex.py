#!/usr/bin/env python3
"""Codex PreToolUse adapter.

Codex documents tool_name, tool_input, cwd, and hook_event_name as the public
payload. The adapter also accepts older observed shapes so a host upgrade does
not silently turn a field rename into a gap. When it cannot find a command or
path at all it fails open rather than blocking work it does not understand.

Every fail-open goes through guard_adapter, so it exits 0 AND leaves a line in
~/.claude/guard-failopen.log saying why. This file used to have three private
fail-open paths that exited silently, and a non-UTF-8 payload made it exit 1
with a traceback, which the host reads as "allowed" just the same.

Set GUARD_CODEX_DEBUG=1 to append every payload it receives to
~/.codex/guard-codex-payloads.jsonl. That file will contain secrets if a
payload did, so it is opt-in, written 0600, and worth deleting after use.

Exit 2 = block, with the reason on stderr. Exit 0 = allow.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import block, fail_open, load_rules, read_payload, verdict  # noqa: E402

# Deliberately no FILE_TOOLS allow-list. Codex exposes local function and MCP
# tools through the same hook path, so any payload carrying a path is checked.
# Only the read/write distinction depends on the tool name.
READ_ONLY_TOOLS = {"read", "readfile", "readtextfile", "readmediafile",
                   "readmultiplefiles", "view", "viewimage", "cat", "open"}

CMD_KEYS = (
    ("tool_input", "command"), ("tool_input", "cmd"), ("tool_input", "script"),
    ("toolInput", "command"), ("input", "command"), ("arguments", "command"),
    ("params", "command"), ("args", "command"), ("command",), ("cmd",),
)
PATH_KEYS = (
    ("tool_input", "file_path"), ("tool_input", "path"),
    ("tool_input", "filename"), ("tool_input", "file"),
    ("tool_input", "paths"), ("tool_input", "source"),
    ("tool_input", "destination"), ("tool_input", "source_path"),
    ("tool_input", "destination_path"), ("tool_input", "old_path"),
    ("tool_input", "new_path"), ("tool_input", "target_file"),
    ("toolInput", "file_path"), ("toolInput", "path"),
    ("toolInput", "paths"), ("input", "file_path"), ("input", "path"),
    ("input", "paths"), ("arguments", "path"),
    ("arguments", "file_path"), ("arguments", "paths"),
    ("file_path",), ("path",), ("paths",), ("source",),
    ("destination",),
)

_PATCH_TOOLS = {"apply_patch", "applypatch"}
_PATCH_PATH = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+?)\s*$|"
    r"^\*\*\* Move to:\s*(.+?)\s*$",
    re.MULTILINE,
)


def debug_log(raw):
    if os.environ.get("GUARD_CODEX_DEBUG") != "1":
        return
    try:
        p = os.path.expanduser("~/.codex/guard-codex-payloads.jsonl")
        # 0600: a payload can carry a token or a file body, and this lands in a
        # long-lived file. Opt-in is not a reason to make it world-readable.
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(raw.strip() + "\n")
    except Exception:                                # noqa: BLE001
        pass


def dig(d, *paths, first=True):
    """Values at the given key paths, walking each one tolerantly.

    `first=True` returns the first non-empty value; `first=False` returns every
    one, flattened. This was two functions with the same walk written twice.

    Tolerant of the wrong shape at every hop: a payload whose `tool_input` is a
    string rather than an object used to raise here, outside any try.
    """
    found = []
    for path in paths:
        cur = d
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if cur:
            if first:
                return cur
            found.extend(cur if isinstance(cur, list) else [cur])
    return None if first else found


def patch_paths(text):
    """Return every source and destination named by an apply_patch payload."""
    if not isinstance(text, str):
        return []
    return [left or right for left, right in _PATCH_PATH.findall(text)]


def main():
    payload = read_payload(debug_log)

    tool = dig(payload, ("tool_name",), ("toolName",), ("tool", "name"))
    tool = tool.lower() if isinstance(tool, str) else ""
    action = tool.rsplit("__", 1)[-1] if tool.startswith("mcp__") else tool
    action = action.replace("_", "").replace("-", "")

    cwd = dig(payload, ("cwd",), ("workdir",), ("workspace_root",))
    if not isinstance(cwd, str) or not cwd:
        if cwd is None:
            cwd = os.getcwd()
        else:
            # Unresolvable, not a reason to allow: the rules already fail
            # CLOSED on a directory they cannot resolve, and we cannot tell
            # which repo the command would have hit.
            cwd = "\0unresolvable-cwd"

    cmd = dig(payload, *CMD_KEYS)
    paths = dig(payload, *PATH_KEYS, first=False)
    raw_input = dig(payload, ("tool_input",), ("toolInput",), ("input",))

    # Codex apply_patch is a free-form tool: tool_input is the patch string,
    # not an object with file_path. Treat each file header as a write target,
    # including Move destinations. Without this branch every patch to .env,
    # .git internals, or the guard's own configuration failed open.
    if tool in _PATCH_TOOLS:
        paths = patch_paths(raw_input if isinstance(raw_input, str) else cmd)
        if not paths:
            fail_open("no file header found in apply_patch payload",
                      str(raw_input)[:200])
        guard_rules = load_rules()
        for candidate in paths:
            hit = verdict(guard_rules.check_path, candidate, True)
            if hit:
                block(*hit)
        sys.exit(0)

    if not cmd and not paths:
        fail_open("no command or path found in payload",
                  ",".join(sorted(payload)[:12]))

    guard_rules = load_rules()

    if cmd:
        # argv lists pass through unchanged: check_command joins them with
        # shlex.join. The plain `" ".join` this file used to do threw away the
        # argument boundaries argv had already established, which stopped nine
        # liability commands blocking on this host and not the other.
        hit = verdict(guard_rules.check_command, cmd, cwd)
        if hit:
            block(*hit)

    if paths:
        writing = action not in READ_ONLY_TOOLS
        # EVERY path, not just the first: a list whose secret sat at index 1
        # was allowed, and the same list reversed blocked.
        for p in paths:
            if not p:
                continue
            hit = verdict(guard_rules.check_path, str(p), writing)
            if hit:
                block(*hit)
    sys.exit(0)


if __name__ == "__main__":
    main()
