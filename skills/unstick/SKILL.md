---
name: unstick
description: Resolve an in-progress Git merge, rebase, cherry-pick, or revert conflict without discarding either side's intent. Use when Git reports conflicts or an operation cannot continue.
---

# Unstick

Resolve the operation already in progress. Do not abort, reset, or choose one side wholesale unless the user explicitly decides to do so.

## Establish state

Inspect `git status`, the current operation, the branch being rewritten, and the conflict list. During a rebase, HEAD is detached, so recover the target branch through Git's own paths:

```bash
B=$(git branch --show-current)
[ -z "$B" ] && B=$(sed -n '1p' "$(git rev-parse --git-path rebase-merge/head-name)" 2>/dev/null \
  || sed -n '1p' "$(git rev-parse --git-path rebase-apply/head-name)" 2>/dev/null)
B=${B#refs/heads/}
```

If the target is `main`, `master`, `prod`, `production`, `trunk`, or `release`, or cannot be determined, stop. Continuing writes history and the guard deliberately cannot block every `--continue` form without trapping legal exits.

## Recover intent

For each conflict, read the surrounding code, both stages, relevant commits, tests, and issue or PR context. Explain what each side was trying to preserve. Resolve the combined intent when compatible. When incompatible, choose the behavior required by the operation's goal and report the tradeoff.

Do not invent unrelated behavior during conflict resolution.

## Verify and continue

Stage only resolved paths by name. Run the closest checks, then the full relevant suite. Continue with the operation-specific command, such as `git rebase --continue` or `git merge --continue`. Repeat until Git reports completion.

If a rebase came from `/ship` in Claude Code or `$ship` in Codex, reuse the exact branch and pre-fetch SHA captured there for the lease push. Never recompute the expected SHA after fetching. If those values are missing or ambiguous, stop and ask.

Finish with the resolved intent, checks run, resulting branch and operation state, and anything that still needs review.
