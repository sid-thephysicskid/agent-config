#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import block, defer_to_cursor, file_access, load_rules, read_payload, verdict  # noqa: E402

def main():
    payload = read_payload()
    defer_to_cursor(payload)
    tool = payload.get("tool_name")
    access = file_access(payload, tool) if isinstance(tool, str) else None
    if not access or not access[0]:
        sys.exit(0)
    paths, writing = access
    guard_rules = load_rules()
    for p in paths:
        hit = verdict(guard_rules.check_path, p, writing, payload.get("tool_input"))
        if hit:
            block(*hit)
    sys.exit(0)

if __name__ == "__main__":
    main()
