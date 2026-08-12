# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
