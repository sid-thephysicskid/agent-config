#!/usr/bin/env python3
"""Cursor preToolUse hook for Shell, Read, Write, Delete, and MCP tools.

Prints Cursor's permission JSON. A deny also exits 2. Anything unexpected allows.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import file_access, load_rules, log, read_payload, verdict  # noqa: E402

def decide(payload):
    tool, args = payload.get("tool_name"), payload.get("tool_input")
    if isinstance(args, str):  # MCP params can arrive as JSON text
        args = payload["tool_input"] = json.loads(args or "{}")
    if not isinstance(tool, str) or not isinstance(args, dict):
        return None
    rules = load_rules()
    if tool == "Shell":
        roots = payload.get("workspace_roots")
        root = roots[0] if isinstance(roots, list) and roots else None
        # Cursor sends cwd as "", so the workspace root is the usual answer.
        cwd = next((c for c in (args.get("cwd"), payload.get("cwd"), root, os.environ.get("CURSOR_PROJECT_DIR"))
                    if isinstance(c, str) and c), os.getcwd())
        return verdict(rules.check_command, args.get("command") or "", cwd)
    paths, writing = file_access(payload, tool.split(":")[-1]) or ((), False)
    for p in paths:
        hit = verdict(rules.check_path, p, writing, args)
        if hit:
            return hit
    return None

def main():
    try:
        hit = decide(read_payload())
    except SystemExit:  # read_payload and verdict exit after logging a fail-open
        hit = None
    except Exception:  # noqa: BLE001
        log("guard-cursor raised", traceback.format_exc(limit=4))
        hit = None
    if not hit:
        print('{"permission": "allow"}')
        sys.exit(0)
    reason, fix = hit
    print(json.dumps({"permission": "deny", "user_message": "BLOCKED: " + reason,
                      "agent_message": "BLOCKED: %s\n\nDo this instead: %s" % (reason, fix)}))
    sys.exit(2)

if __name__ == "__main__":
    main()
