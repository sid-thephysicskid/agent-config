# Agent Config

Use the smallest installed workflow skill that matches the current stage. The
user describes the outcome; they should not have to name a skill.

- Unclear direction or a plan to challenge: `navigate`.
- One unresolved question needing evidence: `prototype`.
- New repository: `bootstrap`. Existing repository with unclear setup: `setup`.
- Decided behavior needing a contract: `to-spec`, then `breakdown` if work must be sliced.
- Unclear business rules or ownership: `domain-modeling`.
- A module boundary or migration: `architect`.
- New behavior or a regression: `tdd`. Unknown failure: `diagnose`.
- Finished changes: `review`, then `ship` when delivery is authorized.
- Git conflict: `unstick`.

Enter at the current stage. Do not replay completed stages or force every task
through the whole sequence. Prefer these workflow skills over overlapping
skills unless the user explicitly names another one. Announce the skill you
use and follow its handoff when the next step is already authorized.

For an adopted repository, keep one real root `AGENTS.md` and a relative
`CLAUDE.md -> AGENTS.md` symlink. `bootstrap` and `setup` establish this. Stop
at approval gates for external, destructive, deployment, merge, or release
actions the user did not authorize.
