# Contributing

## Adding a skill

Apply these rules when proposing a skill:

1. Name the trigger and the job in one sentence.
2. Identify the distinct artifact, decision, or failure mode the skill owns.
3. Show why the host's native behavior or an existing skill does not already handle it well.
4. State its invocation and context cost, plus how its behavior can be tested.
5. Put universal delivery skills in `skills/` and optional operator utilities in `operator-skills/`. The directories are the package boundary.
6. Split when a skill has depth most invocations do not need, not at a byte count.
7. Preserve license and provenance explicitly when code or structure is adapted.

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

```bash
python3 hooks/tests.py --no-perf   # every case, both string and argv forms
python3 hooks/tests.py             # and the wall-clock budgets
```

`--no-perf` omits the timing checks, which are unstable on a loaded machine;
CI runs them in their own job. A hung hook fails OPEN, so those budgets are a
safety gate rather than a speed one.

`hooks/cases.py` has two kinds of case and the distinction is worth keeping.
Most were written against the rules. The block marked THE FLOOR was written
against the JOB, by asking what incident this is for without looking at the
implementation, which is how nine live leaks were found with the rule suite
green.

Every new BLOCK rule needs **two** cases in `hooks/cases.py`: the command it must block, and an ALLOW case for the nearest legitimate command it must not. Without the second one, nothing pins the false-positive direction, and a guard that cries wolf gets switched off.

Verify a new guard, lint rule, or test by introducing a deliberate violation,
confirming failure, then restoring it.

Before opening a PR, run the repository audit:

```bash
python3 tests/audit.py   # no credentials, no personal details, no dead skill links
```

## Commits

`type: description`, lowercase, imperative, no trailing period, subject under 72 characters. Types: `feat`, `fix`, `chore`, `docs`, `test`, `ci`, `refactor`. Small and atomic, each commit a coherent unit.

No em dashes in code, comments, commits, PRs, or docs.
