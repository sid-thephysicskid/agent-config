#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_adapter import block, field, load_rules, read_payload, verdict  # noqa: E402

READ_TOOLS = {"read", "view", "viewfile", "readfile", "readtextfile",
              "readmediafile", "readmultiplefiles", "notebookread"}
WRITE_TOOLS = {"edit", "editfile", "write", "writefile", "multiedit",
               "notebookedit", "update", "strreplace", "createfile",
               "movefile", "renamefile", "deletefile", "removefile",
               "applypatch", "notebookeditcell"}

PATH_KEYS = ("file_path", "notebook_path", "path", "filePath", "target_file",
             "filename", "file", "paths", "source", "destination", "source_path",
             "destination_path", "old_path", "new_path")

def main():
    payload = read_payload()
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        sys.exit(0)
    name = tool.strip().lower()
    action = name.rsplit("__", 1)[-1] if name.startswith("mcp__") else name
    action = action.replace("_", "").replace("-", "")
    if action in READ_TOOLS:
        writing = False
    elif action in WRITE_TOOLS:
        writing = True
    else:
        sys.exit(0)

    paths = []
    for key in PATH_KEYS:
        got = field(payload, "tool_input", key) or field(payload, key)
        if isinstance(got, list):
            paths.extend(str(x) for x in got if x)
        elif got:
            paths.append(got)
    if not paths:
        sys.exit(0)

    guard_rules = load_rules()
    for p in paths:
        hit = verdict(guard_rules.check_path, p, writing, payload.get("tool_input"))
        if hit:
            block(*hit)
    sys.exit(0)

if __name__ == "__main__":
    main()
