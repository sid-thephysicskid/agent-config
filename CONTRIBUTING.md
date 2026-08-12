# Contributing

The suite is deliberately small. Small means each installed capability earns its permanent cost, not that every useful cross-cutting job must fit a lifecycle diagram.

## Adding a skill

Apply these rules when proposing a skill:

1. Name the trigger and the job in one sentence.
2. Identify the distinct artifact, decision, or failure mode the skill owns.
3. Show why the host's native behavior or an existing skill does not already handle it well.
4. State its invocation and context cost, plus how its behavior can be tested.
5. Put universal delivery skills in `skills/` and optional operator utilities in `operator-skills/`. The directories are the package boundary.
6. Split when a skill has depth most invocations do not need, not at a byte count.
7. Preserve license and provenance explicitly when code or structure is adapted.
8. No em dashes. Anywhere. Periods, commas, colons, or a middot.

## Invocation: model-invoked or user-invoked

Before adding a skill, decide whether the model can usefully reach for it on its own. Reuse is not the test.

- **Model-invoked** (the default): the description is loaded on every turn, so
  it is a permanent cost. Worth it when the model, or another skill, genuinely
  needs to reach it.
- **User-invoked**: reserve this for a capability the model must never choose
  on the user's behalf. Keep host metadata in sync and add a parity test.

Every skill needs an `agents/openai.yaml`, or Codex has no way to be told any
of this.

## Changing a guard rule

There are **two** suites, and the split is the point:

```bash
python3 hooks/tests.py --no-perf   # grades the guard against its own rules
python3 hooks/floor.py             # grades the guard against the job
```

Run both. A change that passes only one of them has not been tested. `tests.py` can only assert what somebody already thought of; `floor.py` was written from what a real incident looks like, with the rules deliberately not in view, and its first version found nine live leaks with `tests.py` green. `--no-perf` skips the wall-clock budgets, which flake on a loaded machine and say nothing about correctness. CI runs them on a runner of their own.

Every new BLOCK rule needs **two** cases in `hooks/cases.py`: the command it must block, and an ALLOW case for the nearest legitimate command it must not. Without the second one, nothing pins the false-positive direction, and a guard that cries wolf gets switched off.

A guard, lint rule, or test is not finished until you have watched it fail on a deliberate violation. Break the rule on purpose, see the suite go red, put it back. One that has never gone red is decoration, and you cannot tell the difference by reading it.

Before opening a PR, check that the repo is still publishable:

```bash
python3 tests/audit.py   # no credentials, no personal details, no dead skill links
```

## Commits

`type: description`, lowercase, imperative, no trailing period, subject under 72 characters. Types: `feat`, `fix`, `chore`, `docs`, `test`, `ci`, `refactor`. Small and atomic, each commit a coherent unit.

No em dashes in code, comments, commits, PRs, or docs.
