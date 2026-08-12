#!/usr/bin/env python3
"""Claude Code PreToolUse(Bash) adapter.

Translates Claude's hook payload into guard_rules calls.
Exit 2 = block, stderr goes to the agent. Fails OPEN on any internal error so a
bug here can never brick the CLI, and every fail-open is logged so it cannot go
unnoticed. See guard_adapter.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import block, field, load_rules, read_payload, verdict  # noqa: E402

# Every name a Claude shell tool has used or plausibly could. Gating on the
# single literal "Bash" meant a rename shipped as a total, silent loss of the
# command rules with a green suite.
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
            # A malformed cwd is UNRESOLVABLE, not a reason to allow. The rules
            # already fail CLOSED on a directory they cannot resolve, which is
            # the right answer here: we cannot tell which repo or which tree
            # the command would have hit. A dict used to raise inside
            # os.path.isdir and allow; a list was silently allowed too.
            cwd = "\0unresolvable-cwd"

    guard_rules = load_rules()
    hit = verdict(guard_rules.check_command, cmd, cwd)
    if hit:
        block(*hit)
    sys.exit(0)


if __name__ == "__main__":
    main()
