# Project Instructions

`AGENTS.md` is the canonical instruction file for this repository. Keep
`CLAUDE.md` as a relative symlink to it so Codex, Claude Code, and other agents
receive one shared contract.

## Project contract

Before the first substantive change, replace this generic section with the
project's actual purpose, package boundaries, install command, verification
commands, architecture constraints, release route, and rollback route. Use the
installed `bootstrap` skill for a new repository or `setup` for an existing
one. Record unknowns as unknown instead of guessing.

## Agent workflow

The user describes the outcome. For non-trivial software work, select and use
the installed skill matching the current stage without requiring the user to
name it.

- An unclear idea or disputed plan: `navigate`.
- A question that needs disposable evidence: `prototype`.
- A decided greenfield project: `bootstrap`.
- An existing repository whose commands or delivery path are unclear: `setup`.
- Decided behavior that needs an acceptance contract: `to-spec`.
- A decided specification that needs work items: `breakdown`.
- Unclear business language, rules, states, or ownership: `domain-modeling`.
- A module contract or difficult seam: `architect`.
- New behavior or a regression with a testable seam: `tdd`.
- A hard bug or performance regression: `diagnose`.
- Finished changes that need scrutiny: `review`.
- A merge or rebase conflict: `unstick`.
- Finished work that should land or release: `ship`.

Announce the selected skill and why. Enter the flow at the current stage, do
not repeat completed stages, and follow a skill's handoff when the user already
authorized the next stage. Stop at approval gates for external, destructive,
deployment, merge, or release actions that were not already authorized.
