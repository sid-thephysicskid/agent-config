# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
