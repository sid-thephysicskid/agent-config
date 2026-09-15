#!/usr/bin/env python3
"""UserPromptSubmit hook for Claude Code and Codex: refuse a prompt that carries a credential.

Exit 2 = refused, reason on stderr. Exit 0 = allowed, and on any internal error.
Patterns follow gitleaks.toml. Python 3.9, stdlib only.
"""
import json
import os
import re
import sys
import time

# One regex per kind and no leading \b: a literal prefix lets re skip ahead, 10x faster on 200KB.
KINDS = [(kind, re.compile(pattern, re.ASCII)) for kind, pattern in (
    ("Anthropic API key", r"sk-ant-(?:api03|admin01)-[\w-]{93}AA\b"),
    ("OpenAI API key", r"sk-(?:proj|svcacct|admin)-(?:[\w-]{74}|[\w-]{58})T3BlbkFJ(?:[\w-]{74}|[\w-]{58})\b"),
    ("GitHub token", r"gh[pousr]_[0-9A-Za-z]{36}\b|github_pat_\w{82}\b"),
    ("AWS access key", r"(?:AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16}\b"),
    ("Stripe secret key", r"[sr]k_(?:live|prod)_[A-Za-z0-9]{10,99}\b"),
    ("Slack token", r"xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*|xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}"),
    ("Google API key", r"AIza[\w-]{35}\b"),
    ("npm token", r"npm_[A-Za-z0-9]{36}\b"),
    ("private key", r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY-----"),
)]


def main():
    try:
        prompt = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))["prompt"]
        kind = next((kind for kind, pattern in KINDS if pattern.search(prompt)), None)
    except Exception as error:  # noqa: BLE001
        try:
            os.makedirs(os.path.expanduser("~/.claude"), exist_ok=True)
            # The type only: the payload may hold the very secret we look for.
            with os.fdopen(os.open(os.path.expanduser("~/.claude/guard-failopen.log"),
                                   os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as log:
                log.write("%s guard-prompt failed open: %s\n"
                          % (time.strftime("%Y-%m-%d %H:%M:%S"), type(error).__name__))
        except Exception:  # noqa: BLE001
            pass
        sys.exit(0)
    if kind:
        sys.stderr.write(
            "agent-config: that message looks like it contains a %s. The agent will not act on it, "
            "but the key is exposed now, so rotate it. To give an agent a secret without pasting it, "
            "run this in your own terminal: npx @sid-thephysicskid/agent-config secret NAME\n" % kind)
        sys.exit(2)


if __name__ == "__main__":
    main()
