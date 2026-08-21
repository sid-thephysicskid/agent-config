# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-21

Bugs, and a repository 39% smaller: 29,367 tracked lines to 17831, 236 files
to 108. No guard rule and no test case was removed, and the rule corpus grew
from 1,244 cases to 1,593.

### Fixed

Verification that claimed more than it established:

- `doctor` and `--check` prove the guard still decides, instead of only proving
  it is wired. A rule module that no longer imports leaves every symlink and
  settings entry intact, so the check reported "Guard active" on a machine that
  would have accepted a force push. One probe per rule module, so a single dead
  module is named rather than masked by a neighbour that still answers.
- `doctor` and `--check` surface a non-empty `~/.claude/guard-failopen.log`. The
  guard had recorded every fail-open since it was written and nothing read it.
- The workflow banner counts what is linked instead of printing `13/13`. A
  same-name skill you already had is kept by design, and the banner claimed
  ours was active anyway.
- The skills evaluator fails when its fixtures cannot be built, instead of
  warning and exiting 0, and its summary reports what ran rather than what it
  would have run.
- An argv-shaped tool call reached a different verdict than the same command
  as a string. 66 of the suite's cases disagreed, every one blocking as a
  string and passing as argv, including an inline program deleting a system
  path. The suite now asserts the two agree on every case.
- Five git rules and two filesystem rules stopped applying once a command was
  padded past the analysis window, which the rule that owns that list says
  must never happen.
- The guard's own test fixtures inherited the developer's `~/.gitconfig`. With
  `commit.gpgsign` set, the fixture commits never happen and the suite fails
  for reasons unrelated to the change under test.
- Two of five git-state caches stored the answer given when the subprocess
  budget was spent, freezing it for the rest of the process.

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

- An in-place edit is a write. The unmake list named rm, mv, cp, tee, chmod and
  ln, so the guard could not protect its own configuration from the one verb an
  agent is most likely to reach for when editing a file from a shell.
- Credentials an agent meets inside a container. The credential directory list
  was the dot-directories in a home, so the Docker and Compose secrets mount
  and the Kubernetes service-account token were all readable.
- A client certificate's private half. The flag naming the certificate blocked;
  the flag naming the key did not.
- A script written under a bare name and run with a leading `./` did not join
  up as write-then-run, while the same two segments with matching spellings did.
- A bulk delete of every untracked file, which is the forced clean this guard
  refuses, reached by a different spelling.
- A dry-run flag counted from anywhere in the line, including inside a pathspec
  after `--`, so a forced clean could read as a preview and delete.
- A flag between a wrapper and the binary no longer disables rules anchored on
  the head of the command. Eleven shapes went through, including production
  database connections and inline programs deleting system paths.
- The credential gate detects current issuer formats. It matched an AWS key id
  and never the secret.

Installer:

- The global instructions the installer links carried the skill routing and
  none of the safety rules, so every install produced hooks that block with no
  written policy behind them, and the rules that still apply when the hooks are
  absent were absent too. check-docs now pins the section to AGENTS.md.

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
- Removed the compliance experiment: 4,486 lines with no coupling to the
  product, whose one published result was withdrawn and whose confirmatory run
  was never executed. `evals/README.md` records what was withdrawn and why.
- Merged `hooks/floor.py` into `hooks/cases.py`. Its cases were written against
  the job rather than the rules and that method stays, under a THE FLOOR
  banner; a coverage measurement showed the second file and its second runner
  reached no line the first did not.
- Cut six skill checks that had never produced an error, with the six test
  classes and three scorecard columns that served them. The four that remain
  can all fail.
- One cached, budgeted git question in `hooks/guard_repo.py` instead of five
  copies of it. One key-walker in the Codex adapter instead of two. One
  fixture builder for the evals instead of a second one that scrubbed the
  environment differently.
- The accepted-gap corpus explains each decision once and cites it by tag,
  instead of pasting the same paragraph up to twelve times.

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
