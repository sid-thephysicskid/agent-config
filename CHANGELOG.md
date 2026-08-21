# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

Verification that claimed more than it established:

- `doctor` and `--check` prove the guard still decides, instead of only proving
  it is wired. A rule module that no longer imports leaves every symlink and
  settings entry intact, so the check reported "Guard active" on a machine that
  would have accepted a force push.
- `doctor` and `--check` surface a non-empty `~/.claude/guard-failopen.log`. The
  guard had recorded every fail-open since it was written and nothing read it.
- The workflow banner counts what is linked instead of printing `13/13`. A
  same-name skill you already had is kept by design, and the banner claimed
  ours was active anyway.
- The skills evaluator fails when its fixtures cannot be built, instead of
  warning and exiting 0, and its summary reports what ran rather than what it
  would have run.
- Removed a coverage check that was defined, never wired in, and would have
  failed if it had been.

Guardrails that refused ordinary work:

- A command substitution written inside single quotes is text. Documenting a
  dangerous command was treated as running it.
- A commit message is prose in every spelling, not only `-m`.
- A git dry run is a preview. `clean` with both a dry-run and a force flag
  deletes nothing, and a dry-run push sends nothing.
- A piped bulk delete is judged on where the pipeline is rooted, the same way
  the `-delete` spelling already was.
- A CA bundle named as the trust store to verify with is public by role,
  whatever the file is called.
- Control paths are protected by location, not by filename shape, so a
  throwaway fixture and a second profile are no longer refused.

Guardrails that missed:

- A flag between a wrapper and the binary no longer disables rules anchored on
  the head of the command. Eleven shapes went through, including production
  database connections and inline programs deleting system paths.
- The credential gate detects current issuer formats. It matched an AWS key id
  and never the secret.

Installer:

- Instruction files get a recovery copy before the first edit, and keep their
  line endings. Text between pre-existing markers was destroyed with nothing to
  restore from.
- A dangling Codex `hooks.json` symlink aborts before anything is wired,
  instead of after the whole Claude half.
- A recovery copy is never taken of a file this installer created, so it cannot
  hand back its own writes as the "before" state.
- Uninstall says which deny rules it left behind when the ownership record is
  missing, instead of leaving them silently.

### Added

- `docs/guard-coverage.md`, generated from the rules, with the threat model and
  the accepted gaps. `SECURITY.md` defines a reportable bypass against it.
- `scripts/gates`, one list of every gate, with `--hermetic` to run them
  with nothing inherited from the developer's machine. It replaces two
  drivers that kept two hand-maintained copies of the list and had already
  drifted apart.

### Changed

- Documented the guard-only install, which shipped and was never mentioned.
- Removed the plugin marketplace and the `plugins/` tree: 6,390 lines that
  were 98% a byte-identical copy of `hooks/` and `skills/`, kept in sync by
  hand and policed by six tests, serving an install path that was never
  documented. `npx ... install guard` is the guard-only path.
- Stated the Python and Node floors that are actually tested.

## [0.2.0] - 2026-08-13

### Changed

- Made one install command add guardrails, workflow skills, and automatic routing.
- Added optional extras through `--extras` instead of requiring profile selection.
- Preserved and extended existing agent instructions through a removable managed block.
- Added reversible handling for same-name skills, custom agent homes, and dotfile-managed paths.

## [0.1.1] - 2026-08-12

### Changed

- Reduced the README to purpose, installation, behavior, and verification.
- Replaced decorative graphics with one system diagram.
- Kept third-party attribution concise and license-focused.

## [0.1.0] - 2026-08-12

### Added

- Deterministic pre-tool guardrails for Claude Code and Codex, with explicit
  limits and tested safe alternatives.
- Independent `guard`, `workflow`, `operator`, and `full` install profiles.
- Thirteen delivery skills, plus optional research, credential setup, handoff,
  and communication preferences.
- Shared global instructions and a project initializer that keeps `AGENTS.md`
  canonical and links `CLAUDE.md` to it.
- `npx`, clone-based, and native plugin packaging with selective uninstall.
- Local and CI checks for guard behavior, installers, packages, skills,
  provenance, and documentation.
