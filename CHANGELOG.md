# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Target version: `0.1.0`, the first public beta.

### Added

- A public `npx` installer that stages immutable release files outside npm's cache.
- A history-free public source export with secret, symlink, and package checks.
- An OIDC npm publishing workflow with provenance and no long-lived publish token.
- A concise visual README with an optional agent-context and hook explanation.
- Independent `guard`, `workflow`, `operator`, and composed `full` install profiles with selective uninstall.
- Native `agent-guard`, `agent-workflow`, and `agent-operator` plugin manifests and marketplace metadata for Claude Code and Codex.
- A release builder for standalone, license-complete plugin artifacts.
- Version consistency and plugin execution checks in CI.
- MCP file-tool coverage and Codex free-form patch path inspection.
- Installer validation for every hook event before mutation.
- An exact pinned `force-with-lease` policy and protection against `git push --all`.
- `domain-modeling` as a distinct business-language, invariant, state, and ownership discipline.
- A hardened `wizard` runner with constrained operations and no arbitrary generated shell after secret capture.
- Optional primary-source `research`, cross-session `handoff`, Claude output styles, and Codex communication examples.
- A safe, idempotent `agent-init` command that keeps project `AGENTS.md` canonical and links `CLAUDE.md` to it.
- Automatic global orchestration for clean workflow installs, with an explicit `--skills-only` opt-out and collision-safe fallback.

### Changed

- Reduced the default workflow from an overlapping sixteen-skill suite to thirteen orthogonal delivery skills, with three operator utilities packaged separately.
- Rewrote the remaining skills around distinct lifecycle decisions, observable evidence, pragmatic architecture, and explicit approval gates.
- Rebuilt `setup` as existing-repository adoption across tracker, verification, CI, domain documentation, and release conventions.
- Added focused-design and evidence-based survey modes to `architect` without a separate recurring architecture-report skill.
- Made clean workflow installs share one global orchestration source across Claude Code and Codex without replacing existing user instructions.
- Made all three products independently adoptable while keeping their source and executable contract in one repository.
- Removed Python and Git as installation dependencies for the workflow-only profile.
- Replaced ambiguous provenance claims with an explicit upstream MIT notice.
- Preserved private permissions when shared settings and logs already exist.

### Removed

- The `teach` and `which` skills.
- The session welcome banner, heuristic documentation Stop hook, machine-reset tooling, and HTML workflow map.
- Stale skill reference files and release notes that duplicated active instructions.

### Fixed

- Codex patches could write credential or control files because free-form patch input was not parsed.
- Malformed non-PreToolUse Claude hook events caused partial installation.
- An occupied output-style path caused partial installation.
- Same-size documentation edits shared one Stop-hook suppression key before the heuristic hook was removed.
- Bare or mismatched force-with-lease pushes were broader than the documented exception.
- Existing fail-open logs could remain world-readable after the code changed its creation mode.
- Bare clone installs now match the public `guard` default instead of installing every profile.
- Guard-directory deletion and reused staged-package tampering are now refused.
