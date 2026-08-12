---
name: to-spec
description: Turn an already-decided conversation into a concise specification with acceptance criteria. Use when the user asks to write, capture, or formalize a spec after the important decisions have been made.
---

# To Spec

Synthesize decisions already made. Do not restart discovery or invent missing product choices.

If a missing answer changes the solution, return to `/navigate` in Claude Code or `$navigate` in Codex. If it only affects implementation detail, record it as open with an owner or resolution trigger.

## Write for the implementer and reviewer

Use the project's domain language and existing documentation conventions. A useful specification contains:

```
## Problem
The user-visible problem and evidence it matters.

## Outcome
What will be observably true when complete.

## Scope
Behaviors, users, and systems included.

## Acceptance criteria
Concrete success, failure, permission, and edge-case behavior.

## Decisions
Contracts, data rules, compatibility, rollout, and the reasons behind them.

## Testing and observability
How behavior will be verified and monitored.

## Out of scope
Explicit non-goals.

## Open questions
Only genuine unresolved items, each with an owner or decision trigger.
```

Keep implementation detail out unless it is itself a decided constraint. Prefer stable contracts and domain concepts over file paths.

## Place it deliberately

Do not create a new documentation location by habit. Use an existing issue tracker, specification directory, or architecture record convention. If the user only asked for the text, return it in the conversation. Show the finished spec before filing or publishing it externally.

Finish by naming the source decisions you preserved, assumptions you did not make, and the next step. Hand the spec to `/breakdown` or `$breakdown` for several shippable slices, or to `/architect` or `$architect` when the contract needs module design.
