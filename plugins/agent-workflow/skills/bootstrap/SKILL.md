---
name: bootstrap
description: Create a new repository that can build, test, and ship a minimal vertical slice from day one. Use when starting a project, scaffolding a codebase, or turning an empty directory into a maintainable application.
---

# Bootstrap

Create the smallest repository that proves its delivery path. Do not confuse a large scaffold with a strong foundation.

## Decide the few irreversible things

Confirm the product sentence, primary runtime, deployment environment, persistence needs, and public or private status. Prefer the user's established stack. Choose novelty only when a real requirement pays for its operational cost.

If the product or first slice is unclear, use `/navigate` in Claude Code or `$navigate` in Codex. Do not scaffold an undecided idea.

## Protect existing work

Check whether the directory already contains a repository or meaningful files. If it does, stop treating this as bootstrap and work with what exists. Never initialize over an unknown project.

Initialize version control with an explicit default branch. Create a feature or chore branch before scaffold commits once the initial repository state exists. Do not create a remote, make a repository public, push, provision infrastructure, or deploy without the user's authorization.

Initialize the project instruction contract with the bundled `agent-init`
beside this skill (`../../scripts/agent-init`, resolved from this skill's
directory). The installed `agent-init` command is equivalent. It creates one
canonical root `AGENTS.md` and a relative `CLAUDE.md -> AGENTS.md` symlink. If
either path conflicts, preserve it and report the conflict instead of creating
two instruction sources.

## Build a walking skeleton

Start with one thin path through the real system: a page, request, command, or job that builds and can be exercised. Add only what that path needs.

Include:

- a stack-appropriate `.gitignore`;
- pinned runtime and package manager versions;
- deterministic dependency locking;
- `.env.example` with names only, plus rules that ignore real environment files;
- one meaningful automated test that proves the test command works;
- named commands for build, typecheck, lint, format check, and tests where the stack supports them;
- a minimal CI workflow that runs the same commands;
- a README covering purpose, setup, run, test, and deployment assumptions;
- a root `AGENTS.md` that replaces the initializer's generic project-contract
  section with this repository's actual purpose, package boundaries, commands,
  constraints, release route, rollback route, and known unknowns;
- an appropriate license if the publication intent is known.

Use native framework and platform capabilities before adding dependencies. Keep configuration in conventional locations. Avoid placeholder services, abstract base classes, generated demo pages, and speculative directory trees.

## Security and operations baseline

Use least privilege and local-safe defaults. Never create or inspect real secret files. Add a dependency vulnerability check when the ecosystem has a maintained tool for it.

For a deployable service, include a health signal, structured error logging, and a documented rollback mechanism. Do not claim production readiness from a successful build alone.

## Verify

From a clean checkout state where practical:

1. Install dependencies using the lockfile.
2. Run format check, lint, typecheck, tests, and build.
3. Exercise the walking skeleton as a user would.
4. Inspect the tracked file list for generated output, secrets, and local state.
5. Confirm CI uses the same commands.
6. Run `agent-init --check` or the bundled initializer with `--check`, and
   confirm `CLAUDE.md` is a relative symlink to the canonical `AGENTS.md`.

If deployment is in scope and authorized, deploy the skeleton and verify the live behavior before adding features. Otherwise report exactly what remains unverified.

## Handoff

Summarize the choices, commands, and remaining risks. Use `/architect`, `/tdd`, or `/breakdown` in Claude Code, and `$architect`, `$tdd`, or `$breakdown` in Codex.
