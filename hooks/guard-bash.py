#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import block, field, load_rules, read_payload, verdict  # noqa: E402

SHELL_TOOLS = {"bash", "shell", "run_command", "runcommand", "executecommand"}

def main():
    payload = read_payload()
    tool = payload.get("tool_name")
    if not isinstance(tool, str) or tool.strip().lower() not in SHELL_TOOLS:
        sys.exit(0)

    cmd = field(payload, "tool_input", "command")
    if not cmd:
        sys.exit(0)

    cwd = field(payload, "cwd")
    if not isinstance(cwd, str) or not cwd:
        if payload.get("cwd") is None:
            cwd = os.getcwd()
        else:
            cwd = "\0unresolvable-cwd"

    guard_rules = load_rules()
    hit = verdict(guard_rules.check_command, cmd, cwd)
    if hit:
        block(*hit)
    sys.exit(0)

if __name__ == "__main__":
    main()
