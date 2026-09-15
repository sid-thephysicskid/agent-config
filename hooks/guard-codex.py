#!/usr/bin/env python3
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import block, fail_open, load_rules, read_payload, verdict  # noqa: E402

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
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(raw.strip() + "\n")
    except Exception:                                # noqa: BLE001
        pass

def dig(d, *paths, first=True):
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
            cwd = "\0unresolvable-cwd"

    cmd = dig(payload, *CMD_KEYS)
    paths = dig(payload, *PATH_KEYS, first=False)
    raw_input = dig(payload, ("tool_input",), ("toolInput",), ("input",))

    if tool in _PATCH_TOOLS:
        paths = patch_paths(raw_input if isinstance(raw_input, str) else cmd)
        if not paths:
            fail_open("no file header found in apply_patch payload",
                      str(raw_input)[:200])
        guard_rules = load_rules()
        for candidate in paths:
            hit = verdict(guard_rules.check_path, candidate, True,
                          {"patch": raw_input if isinstance(raw_input, str) else cmd})
            if hit:
                block(*hit)
        sys.exit(0)

    if not cmd and not paths:
        fail_open("no command or path found in payload",
                  ",".join(sorted(payload)[:12]))

    guard_rules = load_rules()

    if cmd:
        hit = verdict(guard_rules.check_command, cmd, cwd)
        if hit:
            block(*hit)

    if paths:
        writing = action not in READ_ONLY_TOOLS
        for p in paths:
            if not p:
                continue
            hit = verdict(guard_rules.check_path, str(p), writing, raw_input)
            if hit:
                block(*hit)
    sys.exit(0)

if __name__ == "__main__":
    main()
