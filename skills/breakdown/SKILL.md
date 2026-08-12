---
name: breakdown
description: Turn a decided approach or specification into small, independently shippable work items. Use when the user asks for issues, tickets, milestones, sequencing, or the first executable slice.
---

# Breakdown

Input is a decided approach. Output is a sequence of work items that can each ship safely.

## Confirm the input is ready

Read the specification, issue, decision, and relevant repository context. If an unresolved choice would materially change the work, return to `/navigate` in Claude Code or `$navigate` in Codex. Do not hide a design decision inside a ticket.

Discover the repository's tracker and conventions from remotes, project files, and existing issues. If the destination is still ambiguous, ask before creating anything. Never guess an organization or repository.

## Slice vertically

Each item should produce an observable capability and leave the default branch working. Avoid separate database, backend, frontend, and test tickets for one behavior.

Order work by risk and learning:

1. The walking skeleton that proves the whole route.
2. High-risk assumptions and irreversible schema or contract choices.
3. User value in dependency order.
4. Hardening and cleanup that cannot belong in an earlier slice.

One item should fit one focused agent session with headroom for tests, review, and surprises. If a vertical slice is still too large, simplify the outcome or identify a coupling problem for `/architect` in Claude Code or `$architect` in Codex.

## Write useful items

Use an imperative outcome for the title. Keep the body compact:

```
Why
Scope
Out of scope
Done when
Dependencies
Risks or rollout notes
```

Acceptance criteria must be observable and testable by someone who did not write the item. Include relevant failure behavior, permissions, migration constraints, and telemetry. Do not prescribe file-by-file implementation unless the specification requires it.

## Preview before external writes

Show the proposed titles, order, dependencies, and walking skeleton before filing issues. Creating many external records is a material action and should not surprise the user.

After approval, use the existing labels and milestones. Pass the destination explicitly when a command could default to an upstream repository. Report created identifiers and anything deliberately deferred.

Hand the first item to `/architect` or `$architect` if its boundary is unresolved, otherwise to `/tdd` or `$tdd`.
