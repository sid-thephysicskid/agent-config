---
name: setup
description: Adopt an existing repository into the workflow by discovering its tracker, project conventions, verification commands, CI, and release path, then filling only material gaps. Use when a repo has not been configured for these skills, its build or issue workflow is unclear, or the user asks to set up CI, project tracking, labels, or agent-facing project docs. Do not use for creating a brand-new repository; use bootstrap instead.
---

# Setup

Make an existing repository legible and verifiable without replacing conventions that already work. Prefer discovery over scaffolding and the smallest useful configuration over a platform.

## 1. Establish the current state

Read before asking:

- repository root, current branch, worktree status, remotes, and fork/upstream relationship;
- root agent instructions and local overrides;
- manifests, lockfiles, task runners, toolchain-version files, and package/workspace layout;
- README and contributor docs for setup, test, lint, build, release, and deploy commands;
- existing CI, required-check documentation, release automation, and deployment configuration;
- issue templates, labels, milestones or projects, and references to an external tracker;
- existing `docs/agents/`, context documents, ADRs, and architecture documentation.

Run the bundled `agent-init` beside this skill (`../../scripts/agent-init`,
resolved from this skill's directory), or the equivalent installed `agent-init`
command. The repository root must use a real `AGENTS.md` as its canonical
instructions and a relative `CLAUDE.md -> AGENTS.md` symlink. The initializer is
idempotent and preserves an existing `AGENTS.md`. If a real `CLAUDE.md`, a wrong
symlink, or another conflict exists, do not overwrite it. Report the exact
conflict and reconcile its content with the user before rerunning the command.

If this is not a repository, hand off to `/bootstrap` in Claude Code or `$bootstrap` in Codex. If setup has already run, report the recorded configuration and repair only stale or missing parts.

Do not read real credential files to discover configuration. Use examples, schemas, manifests, and secret names exposed by CI configuration.

## 2. Reconstruct the verification contract

Identify the exact commands contributors and CI should run for the repository's actual stack:

- dependency installation;
- formatting or formatting checks;
- linting and static analysis;
- type checking;
- unit and integration tests;
- build or packaging;
- any generated-file, migration, or security checks already treated as required.

Prefer commands already exposed by the repository. Resolve conflicting documentation by checking what CI and the package manager execute. Run safe local checks when needed to prove a command works; report commands that require unavailable services instead of pretending they passed.

If there is no CI, propose the smallest workflow that installs locked dependencies and runs the repository's verified commands. Do not add a matrix, cache, release workflow, third-party action, or deployment step without a demonstrated need. Pin third-party actions according to the repository's existing security convention.

If CI exists, preserve its provider and structure. Fix only clear gaps such as a documented required command that CI never runs. Never weaken a required check to make setup green.

## 3. Record the project contract

Create or update the existing equivalents of these files; do not duplicate an established documentation location:

**`docs/agents/project.md`**

- what the repository ships and its package boundaries;
- authoritative install and verification commands;
- CI workflow locations and known required checks;
- release, deployment, and rollback route when discoverable;
- local services or fixtures required by tests;
- unresolved gaps, clearly marked as unknown rather than guessed.

**`docs/agents/issue-tracker.md`**

Start with these machine-readable lines, then explain creation, status, labels, and closure in prose:

```text
Tracker: <github|gitlab|linear|jira|local|other>
Repo: <owner/name or none>
Project: <identifier or none>
```

Record the repository's existing label vocabulary. When none exists, recommend a minimal mapping for `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`; do not create duplicates under new names.

Add or update a short `## Agent project` section in the canonical root
`AGENTS.md` when it materially improves discovery. Point it at the recorded
project contract. Never put independent instructions in `CLAUDE.md`; it remains
the compatibility symlink.

If the initializer created `AGENTS.md`, replace its generic `## Project
contract` section before setup finishes. Either record the repository's actual
purpose, boundaries, commands, constraints, release route, rollback route, and
known unknowns there, or replace the section with a concise pointer to
`docs/agents/project.md`. Do not leave the scaffold instruction in an adopted
repository.

Domain vocabulary does not belong in setup. If it is missing or contradictory, hand it to `/domain-modeling` or `$domain-modeling` after repository setup.

## 4. Separate local configuration from remote mutation

Invoking setup authorizes the necessary local documentation and CI edits on the current feature branch. Before changing any external system, show an exact preview and wait for explicit approval. External changes include:

- creating or editing remote labels, milestones, projects, or issues;
- changing repository settings, branch protection, required checks, secrets, or environments;
- enabling an integration, deployment, or paid service.

The preview must name the target repository or project, every proposed change, whether it is reversible, and the command or API that will perform it. Re-read remote state immediately before applying an approved change and create only what is still missing.

Never request a secret in chat. If setup reaches a credential-only step, hand it to `/wizard` in Claude Code or `$wizard` in Codex.

## 5. Verify and finish

Validate changed configuration syntax and run the documented local verification route in proportion to the edits. Report:

1. what was discovered;
2. local files changed;
3. checks run and their results;
4. external changes made, or still awaiting approval;
5. remaining unknowns or unavailable checks.

Run the initializer with `--check` and include the result. Setup is incomplete
while the two hosts can read different project instructions.

Then use `/domain-modeling` or `$domain-modeling` when the domain language is missing, `/to-spec` or `$to-spec` for a decided change, `/breakdown` or `$breakdown` for an existing spec, or `/navigate` or `$navigate` when the direction is unsettled.
