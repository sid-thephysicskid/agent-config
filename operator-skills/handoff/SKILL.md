---
name: handoff
description: Compact active work into a redacted continuation document for a fresh agent or later session. Use only when the user explicitly asks for a handoff, context transfer, or session continuation note.
---

# Handoff

Write a compact Markdown document that lets a fresh agent continue without
repeating completed work. Save it in the operating system's temporary directory,
not the repository, unless the user names another location.

Include:

- objective and current state;
- decisions made and why;
- completed work and verification results;
- relevant branches, commits, files, issues, or URLs;
- uncommitted or risky state that must be preserved;
- remaining work in execution order;
- blockers, assumptions, and the exact next action;
- skills likely to apply next.

Reference existing specs, plans, ADRs, issues, commits, and diffs instead of
duplicating them. Remove API keys, credentials, personal data, and unnecessary
conversation history. Clearly mark anything unverified.

End the response with the absolute path to the handoff document so it can be
found without searching.
