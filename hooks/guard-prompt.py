#!/usr/bin/env python3
"""Prompt hook for Claude Code and Codex (UserPromptSubmit) and Cursor (beforeSubmitPrompt): refuse a prompt that carries a credential.

Exit 2 = refused, reason on stderr, and for Cursor also on stdout as JSON. Exit 0 = allowed, and on any internal error.
Patterns follow gitleaks.toml. Python 3.9, stdlib only.
"""
import json
import os
import re
import sys

# One regex per kind and no leading \b: a literal prefix lets re skip ahead, 10x faster on 200KB.
KINDS = [(kind, re.compile(pattern, re.ASCII)) for kind, pattern in (
    ("Anthropic API key", r"sk-ant-(?:api03|admin01)-[\w-]{93}AA\b"),
    ("OpenAI API key", r"sk-(?:proj|svcacct|admin)-(?:[\w-]{74}|[\w-]{58})T3BlbkFJ(?:[\w-]{74}|[\w-]{58})\b"),
    ("GitHub token", r"gh[pousr]_[0-9A-Za-z]{36}\b|github_pat_\w{82}\b"),
    ("AWS access key", r"(?:AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16}\b"),
    ("Stripe secret key", r"[sr]k_(?:live|prod)_[A-Za-z0-9]{10,99}\b"),
    ("Slack token", r"xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*|xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}"),
    ("npm token", r"npm_[A-Za-z0-9]{36}\b"),
    ("private key", r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY-----\s*(?:[A-Za-z0-9+/=]\s*){40}"),
)]


def real(key):
    # Doc examples (AWS ids ending in EXAMPLE) and one-character placeholders are not keys.
    return not key.endswith("EXAMPLE") and len(set(re.sub(r"[^A-Za-z0-9]", "", key)[-12:])) > 2


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        prompt = payload["prompt"]
        cursor = payload.get("hook_event_name") == "beforeSubmitPrompt"
        kind = next((kind for kind, pattern in KINDS
                     if any(real(m.group()) for m in pattern.finditer(prompt))), None)
    except Exception as error:  # noqa: BLE001
        # Imported here: guard_adapter costs ~15ms per prompt. Log the type only, never the payload.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from guard_adapter import log
        log("guard-prompt failed open", type(error).__name__)
        sys.exit(0)
    message = kind and (
        "agent-config: that message looks like it contains a %s. The agent will not act on it, "
        "but the key is exposed now, so rotate it. To give an agent a secret without pasting it, "
        "run this in your own terminal: npx @sid-thephysicskid/agent-config secret NAME" % kind)
    if cursor:
        print(json.dumps({"continue": False, "user_message": message} if kind else {"continue": True}))
    if kind:
        sys.stderr.write(message + "\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
