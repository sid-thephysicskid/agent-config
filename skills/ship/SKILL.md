---
name: ship
description: Take finished work through verification, intentional commits, a pull request, CI, approved merge, deployment, and live validation. Use when the user asks to publish changes, open a PR, merge, deploy, release, or land completed work.
---

# Ship

Shipping is a sequence of gates. A failed gate stops the sequence. Report every skipped or unavailable check.

## 1. Establish authority and branch safety

Inspect the current branch, status, remotes, and any in-progress Git operation. Never commit or push from a protected branch. Follow the repository's branch naming convention and preserve unrelated user changes.

Opening a branch, committing in-scope work, pushing that branch, and opening a draft PR are normal parts of an explicit ship request. Merging, deploying, publishing, tagging a release, rewriting history, or changing production state requires explicit user authorization unless it was already clearly granted.

## 2. Understand the complete change

Read the full diff, including staged, unstaged, untracked, and commits since the base. Compare it with the issue or specification. Split unrelated work rather than quietly bundling it. Check for secrets, generated artifacts, debug code, and accidental configuration.

## 3. Run project gates

Discover checks from CI and project configuration. Run cheap checks first, then expensive ones:

1. format check and static analysis;
2. typecheck and build;
3. focused tests, then the relevant full suite;
4. dependency audit when manifests or lockfiles changed;
5. migration and compatibility checks when data contracts changed.

Never skip, weaken, or delete a failing test to get green. Fix the cause and rerun the failed gate.

## 4. Review and verify real behavior

Run `/review` in Claude Code or `$review` in Codex against a fixed diff. Resolve P0 and P1 findings. Resolve P2 findings or record why they are accepted.

Before merging, exercise the changed behavior through its real public path. A unit suite is not enough for a UI flow, API integration, migration, CLI, or deployment change. Use a safe local, preview, or staging environment. Record what was exercised and the result.

## 5. Commit intentionally

Group the finished change into the smallest coherent commits that leave the repository valid. Stage paths deliberately. Use the repository's commit convention. Inspect the staged diff before each commit and verify no user-owned or unrelated work is included.

Do not amend another person's commit or rewrite shared history.

## 6. Push and open the pull request

Push the current branch with upstream tracking. Open a draft pull request unless the user asked for a ready review. Include:

- problem and outcome;
- significant decisions;
- tests and real behavior verification;
- migration, rollout, and rollback notes;
- known risks and deliberately deferred work.

Do not claim a check passed if it was not run.

## 7. Watch CI

Wait for all required checks. Investigate failures from logs, fix them on the branch, rerun local checks, and push. Do not treat a flaky retry as a fix without evidence.

If the branch must be rebased, capture both values before fetching:

```bash
BRANCH=$(git branch --show-current)
BEFORE=$(git rev-parse "origin/$BRANCH")
```

After a successful rebase and verification, substitute the two recorded literal values into `git push --force-with-lease=<branch>:<full-before-sha>`. Do not rely on shell variables from an earlier tool call. If another commit reached the branch, the lease must fail. Never replace it with a bare lease or force push.

## 8. Approval and merge

Present the PR, review result, CI state, behavior verification, rollout risk, and merge method. Wait for explicit approval to merge. Respect required human reviewers and branch protection. Never use an admin bypass to make a red or unapproved PR merge.

## 9. Deploy and verify

If merge triggers deployment, watch the actual deployment. If deployment is manual, obtain authorization before starting it. Verify the live version and changed behavior from the user's perspective, plus relevant health and error signals.

For risky changes, confirm the rollback route before deployment. If verification fails, stop rollout or propose rollback with blast radius and evidence. Do not mutate production merely because a dashboard is noisy.

## 10. Close honestly

Report commits, PR, CI, merge, deployment, live verification, and cleanup. Include a `Not done` section for every gate that was skipped, unavailable, or out of scope. The task is complete only at the last gate the user authorized, not at the first green build.
